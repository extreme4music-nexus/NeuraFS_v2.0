/**
 * NeuraFS Single-User Web Storage Explorer Backend (Express.js)
 */

const express = require('express');
const fs = require('fs');
const path = require('path');
const multer = require('multer');

// Updated relative path pointing to neurafs/sdk/node/hyper-compress-sdk.js
const NeuraFSSDK = require('../neurafs/sdk/node/hyper-compress-sdk');

const app = express();
const PORT = process.env.PORT || 3000;
const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:8000';

const sdk = new NeuraFSSDK(PYTHON_API_URL);

// Root directory paths relative to web/
const STORAGE_ROOT = path.join(__dirname, '..', 'storage');
const TEMP_ROOT = path.join(STORAGE_ROOT, '.temp');
const PUBLIC_DIR = path.join(__dirname, 'public');

const activeTasks = {};

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(PUBLIC_DIR));

const upload = multer({ dest: TEMP_ROOT });

function initializeDirectories() {
    [
        STORAGE_ROOT,
        TEMP_ROOT,
        path.join(STORAGE_ROOT, 'media'),
        path.join(STORAGE_ROOT, 'documents'),
        PUBLIC_DIR
    ].forEach(dir => {
        if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    });
}

function calculateFolderSize(dirPath) {
    if (!fs.existsSync(dirPath)) return 0;
    let total = 0;
    const items = fs.readdirSync(dirPath, { withFileTypes: true });

    for (const item of items) {
        if (item.name.startsWith('.')) continue;
        const abs = path.join(dirPath, item.name);
        if (item.isDirectory()) total += calculateFolderSize(abs);
        else total += fs.statSync(abs).size;
    }
    return total;
}

/**
 * Recursively inspects VFS directory tree reading container manifests.
 */
function buildDirectoryTree(dirPath, relativePath = '') {
    if (!fs.existsSync(dirPath)) return [];
    const items = fs.readdirSync(dirPath, { withFileTypes: true });
    const tree = [];

    for (const item of items) {
        if (item.name.startsWith('.')) continue;

        const itemRelPath = path.join(relativePath, item.name).replace(/\\/g, '/');
        const itemAbsPath = path.join(dirPath, item.name);

        if (item.isDirectory()) {
            tree.push({
                name: item.name,
                path: itemRelPath,
                type: 'folder',
                children: buildDirectoryTree(itemAbsPath, itemRelPath)
            });
        } else if (item.name.endsWith('.hcs')) {
            try {
                const manifest = sdk.readManifest(itemAbsPath);
                const stats = fs.statSync(itemAbsPath);

                const origInfo = manifest.original || {};
                const neuralInfo = manifest.neural || {};
                const metrics = manifest.metrics || {};

                const originalName = origInfo.name || item.name.slice(0, -4);
                const isMedia = origInfo.type === 'neural_media' || /\.(wav|mp3|flac|mp4|mkv|avi)$/i.test(originalName);

                const origSize = origInfo.size || stats.size * 2;
                const compSize = stats.size;
                const ratioVal = origSize > compSize ? ((1 - compSize / origSize) * 100).toFixed(1) + '%' : '1:1';

                tree.push({
                    name: originalName,
                    hcs_file_name: item.name,
                    path: itemRelPath,
                    type: 'file',
                    file_category: isMedia ? 'media' : 'document',
                    original_size: origSize,
                    compressed_size: compSize,
                    precision: neuralInfo.precision || 'fp16',
                    metrics: metrics,
                    created_at: stats.birthtime,
                    compression_ratio: ratioVal
                });
            } catch (err) {
                continue;
            }
        }
    }
    return tree;
}

app.get('/api/fs/tree', (req, res) => {
    try {
        const tree = buildDirectoryTree(STORAGE_ROOT);
        const totalUsed = calculateFolderSize(STORAGE_ROOT);
        res.json({ status: 'success', root: tree, used_bytes: totalUsed });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/fs/folder', (req, res) => {
    try {
        const { folderPath } = req.body;
        if (!folderPath) return res.status(400).json({ error: 'Folder path is required' });

        const targetDir = path.join(STORAGE_ROOT, folderPath);
        if (!fs.existsSync(targetDir)) {
            fs.mkdirSync(targetDir, { recursive: true });
            return res.json({ status: 'success', message: 'Folder created', path: folderPath });
        }
        res.status(400).json({ error: 'Folder already exists' });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.delete('/api/fs/item', (req, res) => {
    try {
        const { targetPath } = req.body;
        if (!targetPath) return res.status(400).json({ error: 'Target path is required' });

        const cleanPath = targetPath.split('?')[0];
        const absPath = path.join(STORAGE_ROOT, cleanPath);
        
        if (fs.existsSync(absPath + '.hcs')) {
            fs.unlinkSync(absPath + '.hcs');
        } else if (fs.existsSync(absPath)) {
            fs.rmSync(absPath, { recursive: true, force: true });
        } else {
            return res.status(404).json({ error: 'Item not found' });
        }

        res.json({ status: 'success', message: 'Item deleted successfully' });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/api/fs/tasks-status', (req, res) => {
    res.json(activeTasks);
});

app.post('/api/fs/upload-async', upload.any(), async (req, res) => {
    const files = req.files || (req.file ? [req.file] : []);
    if (!files.length) return res.status(400).json({ error: 'No files uploaded' });

    const taskId = req.body.taskId || ('task_' + Date.now());
    const precisionMode = req.body.precisionMode || 'fp16';
    const computeDevice = req.body.computeDevice || 'cpu';

    const file = files[0];
    res.json({ status: 'processing', taskId, message: 'Neural parameterization initiated' });

    activeTasks[taskId] = {
        id: taskId,
        fileName: file.originalname,
        progress: 5,
        log: `Initiating Neural Parameterization...`,
        logsHistory: [`[NeuraFS Express] Mode: ${precisionMode.toUpperCase()} | Device: ${computeDevice.toUpperCase()}`],
        status: 'running'
    };

    try {
        const formData = new FormData();
        const fileBuffer = fs.readFileSync(file.path);
        const blob = new Blob([fileBuffer], { type: 'application/octet-stream' });
        formData.append('file', blob, file.originalname);
        formData.append('task_id', taskId);
        formData.append('precision_mode', precisionMode);
        formData.append('compute_device', computeDevice);

        const startRes = await fetch(`${PYTHON_API_URL}/api/v1/encode-neural-media-start`, {
            method: 'POST',
            body: formData
        });

        if (!startRes.ok) throw new Error(`API Error [Neural Start]: ${startRes.statusText}`);

        while (true) {
            await new Promise(r => setTimeout(r, 600));
            const statusRes = await fetch(`${PYTHON_API_URL}/api/v1/task-status/${taskId}`);
            const statusData = await statusRes.json();

            activeTasks[taskId] = {
                id: taskId,
                fileName: file.originalname,
                progress: statusData.progress || 10,
                log: statusData.log || 'Processing...',
                logsHistory: statusData.logsHistory || [],
                status: statusData.status
            };

            if (statusData.status === 'completed') {
                break;
            } else if (statusData.status === 'failed' || statusData.status === 'cancelled') {
                throw new Error(statusData.log || 'Neural encoding failed.');
            }
        }

        if (fs.existsSync(file.path)) fs.unlinkSync(file.path);

        if (activeTasks[taskId]) {
            activeTasks[taskId].progress = 100;
            activeTasks[taskId].log = 'Neural parameterization complete!';
            activeTasks[taskId].status = 'completed';
            setTimeout(() => { delete activeTasks[taskId]; }, 3000);
        }

    } catch (error) {
        if (fs.existsSync(file.path)) fs.unlinkSync(file.path);
        if (activeTasks[taskId]) {
            activeTasks[taskId].status = 'failed';
            activeTasks[taskId].log = `Error: ${error.message}`;
        }
    }
});

app.get('/api/fs/stream', async (req, res) => {
    const rawPath = req.query.path;
    if (!rawPath) return res.status(400).send('File path required');

    let absPath = path.join(STORAGE_ROOT, rawPath);
    if (!absPath.endsWith('.hcs')) absPath += '.hcs';

    if (!fs.existsSync(absPath)) return res.status(404).send('File not found');

    try {
        const { buffer, originalName } = await sdk.decompressToBuffer(absPath);
        const ext = path.extname(originalName).toLowerCase();
        let contentType = 'application/octet-stream';

        if (['.txt', '.csv', '.log'].includes(ext)) contentType = 'text/plain';
        else if (ext === '.json') contentType = 'application/json';
        else if (ext === '.pdf') contentType = 'application/pdf';
        else if (['.wav', '.mp3', '.ogg', '.flac'].includes(ext)) contentType = 'audio/wav';

        res.setHeader('Content-Type', contentType);
        res.setHeader('Content-Disposition', `inline; filename="${originalName}"`);
        res.send(buffer);
    } catch (error) {
        res.status(500).send(`Resynthesis error: ${error.message}`);
    }
});

app.get('/api/fs/download/raw', async (req, res) => {
    const rawPath = req.query.path;
    if (!rawPath) return res.status(400).send('File path required');

    let absPath = path.join(STORAGE_ROOT, rawPath);
    if (!absPath.endsWith('.hcs')) absPath += '.hcs';

    if (!fs.existsSync(absPath)) return res.status(404).send('File not found');

    try {
        const { buffer, originalName } = await sdk.decompressToBuffer(absPath);
        res.setHeader('Content-Type', 'application/octet-stream');
        res.setHeader('Content-Disposition', `attachment; filename="${originalName}"`);
        res.send(buffer);
    } catch (error) {
        res.status(500).send(`Download error: ${error.message}`);
    }
});

app.use((req, res) => {
    res.sendFile(path.join(PUBLIC_DIR, 'index.html'));
});

app.listen(PORT, () => {
    initializeDirectories();
    console.log(`===================================================`);
    console.log(` NeuraFS Web Explorer Server Active on Port ${PORT}`);
    console.log(`===================================================`);
});