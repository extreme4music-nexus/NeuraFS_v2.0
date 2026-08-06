/**
 * NeuraFS Single-User Web Storage Explorer Backend (Express.js)
 * Safe Multer Disk Storage & Dynamic Universal Path Engine
 */

const express = require('express');
const fs = require('fs');
const path = require('path');
const os = require('os');
const multer = require('multer');

// 1. Динамичко читање на патеката од StorageManager (~/.neurafs/config.json)
function getUniversalStorageRoot() {
    const configPath = path.join(os.homedir(), '.neurafs', 'config.json');
    if (fs.existsSync(configPath)) {
        try {
            const configData = JSON.parse(fs.readFileSync(configPath, 'utf8'));
            if (configData.storage_path) {
                return path.resolve(configData.storage_path);
            }
        } catch (err) {
            console.warn('[NeuraFS Web] Неуспешно читање на ~/.neurafs/config.json, се користи default патека.');
        }
    }
    return path.resolve(path.join(__dirname, '..', '..', 'storage'));
}

const STORAGE_ROOT = getUniversalStorageRoot();
const TEMP_ROOT = path.resolve(path.join(STORAGE_ROOT, '.temp'));
const PUBLIC_DIR = path.resolve(path.join(__dirname, 'public'));

// 2. Гарантирано синхроно креирање на Системските директориуми
function ensureDirectoriesExist() {
    [
        STORAGE_ROOT,
        TEMP_ROOT,
        path.join(STORAGE_ROOT, 'media'),
        path.join(STORAGE_ROOT, 'documents'),
        PUBLIC_DIR
    ].forEach(dir => {
        const absDir = path.resolve(dir);
        if (!fs.existsSync(absDir)) {
            fs.mkdirSync(absDir, { recursive: true });
        }
    });
}
ensureDirectoriesExist();

const NeuraFSSDK = require('../sdk/node/hyper-compress-sdk');

const app = express();
const PORT = process.env.PORT || 3000;
const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://127.0.0.1:8000';

const sdk = new NeuraFSSDK(PYTHON_API_URL);
const activeTasks = {};

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(PUBLIC_DIR));

// 3. Сигурна Multer DiskStorage Конфигурација со нормализирана патека
const storageConfig = multer.diskStorage({
    destination: (req, file, cb) => {
        ensureDirectoriesExist();
        cb(null, TEMP_ROOT);
    },
    filename: (req, file, cb) => {
        const safeName = file.originalname.replace(/[^a-zA-Z0-9._-]/g, '_');
        cb(null, `${Date.now()}-${safeName}`);
    }
});

const upload = multer({ storage: storageConfig });

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
                const header = sdk.readHcsHeader ? sdk.readHcsHeader(itemAbsPath) : sdk.readManifest(itemAbsPath);
                const stats = fs.statSync(itemAbsPath);

                if (header.type === 'folder_bundle') {
                    const childNodes = (header.files || []).map(f => ({
                        name: f.original_name,
                        hcs_file_name: item.name,
                        sub_path: f.relative_path,
                        path: `${itemRelPath}?subpath=${encodeURIComponent(f.relative_path)}`,
                        type: 'file',
                        file_category: (f.type === 'neural_media' || f.type === 'neural_video') ? 'media' : 'document',
                        original_size: f.original_size,
                        compressed_size: Math.round(stats.size / (header.files.length || 1)),
                        created_at: header.created_at || stats.birthtime,
                        compression_ratio: `${((1 - stats.size / (header.original_size || stats.size)) * 100).toFixed(1)}%`
                    }));

                    tree.push({
                        name: header.folder_name || item.name.slice(0, -4),
                        path: itemRelPath,
                        type: 'folder',
                        children: childNodes
                    });
                } else {
                    const originalName = header.original_filename || header.original_name || (header.original && header.original.name) || item.name.slice(0, -4);
                    const isMedia = (header.type === 'neural_media' || header.type === 'neural_video') ||
                                    /\.(wav|mp3|flac|mp4|mkv|avi|ogg|mov)$/i.test(originalName);

                    const origSize = header.original_size || (header.original && header.original.size) || stats.size * 2;
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
                        created_at: header.created_at || stats.birthtime,
                        compression_ratio: ratioVal
                    });
                }
            } catch (err) {
                continue;
            }
        }
    }
    return tree;
}

// REST API Endpoints
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

app.post('/api/fs/task-cancel', (req, res) => {
    const { taskId } = req.body;
    if (!taskId) return res.status(400).json({ error: 'taskId is required' });

    if (taskId === 'all') {
        Object.keys(activeTasks).forEach(id => {
            activeTasks[id].status = 'cancelled';
            activeTasks[id].log = 'Task cancelled by user.';
        });
        return res.json({ status: 'success', message: 'All active tasks cancelled.' });
    }

    if (activeTasks[taskId]) {
        activeTasks[taskId].status = 'cancelled';
        activeTasks[taskId].log = 'Task cancelled by user.';
        return res.json({ status: 'success', message: `Task ${taskId} cancelled.` });
    }

    res.json({ status: 'success', message: 'Task removed or already completed.' });
});

app.post('/api/fs/upload-async', upload.any(), async (req, res) => {
    const files = req.files || (req.file ? [req.file] : []);
    if (!files.length) return res.status(400).json({ error: 'No files uploaded' });

    const taskId = req.body.taskId || ('task_' + Date.now());
    const precisionMode = req.body.precisionMode || 'auto';
    const computeDevice = req.body.computeDevice || 'cpu';
    const parallelEnabled = req.body.parallelEnabled !== 'false';

    const relativePaths = [].concat(req.body.relativePaths || req.body.relativePath || []);
    const userTargetFolder = req.body.targetFolder || 'documents';
    const isFolderBundle = files.length > 1 || relativePaths.length > 0;

    res.json({ status: 'processing', taskId, message: 'Neural parameterization initiated' });

    activeTasks[taskId] = {
        id: taskId,
        fileName: isFolderBundle ? 'Folder Bundle' : files[0].originalname,
        progress: 5,
        log: `Initiating Neural Parameterization...`,
        logsHistory: [`[NeuraFS Node.js] Mode: ${precisionMode.toUpperCase()} | Device: ${computeDevice.toUpperCase()}`],
        status: 'running'
    };

    try {
        const onProgress = (progressPercent, statusLog, pythonLogs) => {
            if (activeTasks[taskId] && activeTasks[taskId].status === 'cancelled') {
                throw new Error('Task cancelled by user.');
            }
            activeTasks[taskId] = {
                id: taskId,
                fileName: isFolderBundle ? 'Folder Bundle' : files[0].originalname,
                progress: progressPercent,
                log: statusLog,
                logsHistory: ['[NeuraFS Express] Processing Neural Subbands...', ...(pythonLogs || [])],
                status: 'running'
            };
        };

        if (isFolderBundle && files.length > 1 && typeof sdk.compressFolderBundle === 'function') {
            const folderName = relativePaths[0] ? relativePaths[0].split('/')[0] : 'Uploaded_Folder';
            const fileItems = files.map((f, i) => ({
                tempFilePath: path.resolve(f.path),
                originalName: f.originalname,
                relativePath: relativePaths[i] || f.originalname
            }));

            const destDir = path.join(STORAGE_ROOT, userTargetFolder);
            await sdk.compressFolderBundle(fileItems, destDir, folderName, taskId, onProgress, precisionMode, computeDevice, parallelEnabled);
            fileItems.forEach(f => { if (fs.existsSync(f.tempFilePath)) fs.unlinkSync(f.tempFilePath); });

        } else {
            const file = files[0];
            const filePath = path.resolve(file.path);
            const isMedia = /\.(wav|mp3|flac|mp4|mkv|avi|ogg|mov)$/i.test(file.originalname);
            const autoFolder = isMedia ? 'media' : userTargetFolder;
            const destDir = path.join(STORAGE_ROOT, autoFolder);
            if (!fs.existsSync(destDir)) fs.mkdirSync(destDir, { recursive: true });

            if (typeof sdk.compressFile === 'function') {
                await sdk.compressFile(filePath, destDir, file.originalname, taskId, onProgress, precisionMode, computeDevice, parallelEnabled);
            }
            if (fs.existsSync(filePath)) fs.unlinkSync(filePath);
        }

        if (activeTasks[taskId] && activeTasks[taskId].status !== 'cancelled') {
            activeTasks[taskId].progress = 100;
            activeTasks[taskId].log = 'Neural parameterization complete!';
            activeTasks[taskId].status = 'completed';
            setTimeout(() => { delete activeTasks[taskId]; }, 3000);
        }

    } catch (error) {
        files.forEach(f => { 
            const p = path.resolve(f.path);
            if (fs.existsSync(p)) fs.unlinkSync(p); 
        });
        if (activeTasks[taskId]) {
            if (activeTasks[taskId].status === 'cancelled') {
                setTimeout(() => { delete activeTasks[taskId]; }, 1000);
            } else {
                activeTasks[taskId].status = 'failed';
                activeTasks[taskId].log = `Error: ${error.message}`;
            }
        }
    }
});

app.get('/api/fs/stream', async (req, res) => {
    const rawPath = req.query.path;
    if (!rawPath) return res.status(400).send('File path required');

    const pathParts = rawPath.split('?subpath=');
    const relPath = pathParts[0];
    const subPath = pathParts[1] ? decodeURIComponent(pathParts[1]) : null;

    let absPath = path.join(STORAGE_ROOT, relPath);
    if (!fs.existsSync(absPath) && fs.existsSync(absPath + '.hcs')) absPath += '.hcs';

    if (!fs.existsSync(absPath)) return res.status(404).send('File not found');

    try {
        const { buffer, originalName } = await sdk.decompressToBuffer(absPath, subPath);
        const ext = path.extname(originalName).toLowerCase();
        let contentType = 'application/octet-stream';

        if (['.txt', '.csv', '.log'].includes(ext)) contentType = 'text/plain';
        else if (ext === '.json') contentType = 'application/json';
        else if (ext === '.pdf') contentType = 'application/pdf';
        else if (['.wav', '.mp3', '.ogg', '.flac'].includes(ext)) contentType = 'audio/wav';
        else if (['.mp4', '.mkv', '.avi'].includes(ext)) contentType = 'video/mp4';

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

    const pathParts = rawPath.split('?subpath=');
    const relPath = pathParts[0];
    const subPath = pathParts[1] ? decodeURIComponent(pathParts[1]) : null;

    let absPath = path.join(STORAGE_ROOT, relPath);
    if (!fs.existsSync(absPath) && fs.existsSync(absPath + '.hcs')) absPath += '.hcs';

    if (!fs.existsSync(absPath)) return res.status(404).send('File not found');

    try {
        const { buffer, originalName } = await sdk.decompressToBuffer(absPath, subPath);
        res.setHeader('Content-Type', 'application/octet-stream');
        res.setHeader('Content-Disposition', `attachment; filename="${originalName}"`);
        res.send(buffer);
    } catch (error) {
        res.status(500).send(`Download error: ${error.message}`);
    }
});

app.get('/api/fs/download/compressed', (req, res) => {
    const rawPath = req.query.path;
    if (!rawPath) return res.status(400).send('File path required');

    const cleanPath = rawPath.split('?')[0];
    let absPath = path.join(STORAGE_ROOT, cleanPath);
    if (!fs.existsSync(absPath) && fs.existsSync(absPath + '.hcs')) absPath += '.hcs';

    if (!fs.existsSync(absPath)) return res.status(404).send('File not found');

    const fileName = path.basename(absPath);
    res.setHeader('Content-Type', 'application/octet-stream');
    res.setHeader('Content-Disposition', `attachment; filename="${fileName}"`);
    res.sendFile(absPath);
});

app.use((req, res) => {
    res.sendFile(path.join(PUBLIC_DIR, 'index.html'));
});

// Експлицитно 127.0.0.1 слушање
app.listen(PORT, '127.0.0.1', () => {
    console.log(`===================================================`);
    console.log(` NeuraFS Single-User Web Engine Active on Port ${PORT}`);
    console.log(` Access URL: http://127.0.0.1:${PORT}`);
    console.log(`===================================================`);
});