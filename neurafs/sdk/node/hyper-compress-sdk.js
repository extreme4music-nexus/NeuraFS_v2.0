/**
 * NeuraFS Node.js Universal SDK
 * Supports HCS1 LZMA Container Unpacking, Subband Audio Resynthesis,
 * Multi-file Folder Bundles, and Safe Memory Buffer Management.
 */

const fs = require('fs');
const path = require('path');
const lzma = require('lzma-native');

/**
 * Unpacks raw .hcs binary buffer based on 12-byte HCS1 header spec.
 * Header format: Magic "HCS1" (4B) | Flags (4B) | Manifest Length UInt32BE (4B)
 */
function unpackHcsBuffer(fileBuffer) {
    try {
        const decompressed = lzma.decompress(fileBuffer);

        if (decompressed.length < 12) {
            throw new Error('Container smaller than mandatory 12-byte header.');
        }

        const magic = decompressed.subarray(0, 4).toString('utf-8');
        if (magic === 'HCS1') {
            const flags = decompressed.subarray(4, 8);
            const metaLen = decompressed.readUInt32BE(8);

            const manifestJson = decompressed.subarray(12, 12 + metaLen).toString('utf-8');
            const manifest = JSON.parse(manifestJson);
            const rawBlobs = decompressed.subarray(12 + metaLen);

            return { manifest, rawBlobs, flags };
        }

        throw new Error(`Invalid magic identifier: ${magic}`);
    } catch (err) {
        throw new Error(`Failed to unpack HCS container: ${err.message}`);
    }
}

class NeuraFSSDK {
    /**
     * @param {string} apiBaseUrl - Base HTTP URL for NeuraFS FastAPI backend engine
     */
    constructor(apiBaseUrl = 'http://127.0.0.1:8000') {
        this.apiBaseUrl = apiBaseUrl;
    }

    /**
     * Detects category (media vs binary document) based on file extension.
     */
    detectFileType(filePath) {
        const ext = path.extname(filePath).toLowerCase();
        const mediaExtensions = ['.mp3', '.wav', '.flac', '.ogg', '.mp4', '.avi', '.mkv', '.mov'];
        return mediaExtensions.includes(ext) ? 'media' : 'binary';
    }

    /**
     * Reads and parses metadata manifest from .hcs container without decompressing weight blobs.
     */
    readManifest(hcsFilePath) {
        if (!fs.existsSync(hcsFilePath)) {
            throw new Error(`Target HCS file not found: ${hcsFilePath}`);
        }
        const fileBuffer = fs.readFileSync(hcsFilePath);
        const { manifest } = unpackHcsBuffer(fileBuffer);
        return manifest;
    }

    /**
     * Alias method for backward compatibility with Web Explorer API.
     */
    readHcsHeader(hcsFilePath) {
        return this.readManifest(hcsFilePath);
    }

    /**
     * Encodes single file asynchronously via NeuraFS API Engine with status tracking.
     */
    async compressFile(inputPath, targetDir, overrideOriginalName = null, taskId = null, onProgress = null, precisionMode = 'fp16', computeDevice = 'cpu', parallelEnabled = true) {
        if (!fs.existsSync(inputPath)) {
            throw new Error(`Input file not found at path: ${inputPath}`);
        }

        const originalName = overrideOriginalName || path.basename(inputPath);
        const activeTaskId = taskId || ('task_' + Date.now());
        const rawBuffer = fs.readFileSync(inputPath);

        const formData = new FormData();
        const blob = new Blob([rawBuffer], { type: 'application/octet-stream' });
        formData.append('file', blob, originalName);
        formData.append('task_id', activeTaskId);
        formData.append('precision_mode', precisionMode);
        formData.append('compute_device', computeDevice);
        formData.append('parallel_enabled', String(parallelEnabled));

        const startRes = await fetch(`${this.apiBaseUrl}/api/v1/encode-neural-media-start`, {
            method: 'POST',
            body: formData
        });

        if (!startRes.ok) {
            throw new Error(`API Error [Neural Start]: ${startRes.statusText}`);
        }

        let apiResult = null;
        while (true) {
            await new Promise(r => setTimeout(r, 500));
            const statusRes = await fetch(`${this.apiBaseUrl}/api/v1/task-status/${activeTaskId}`);
            const statusData = await statusRes.json();

            if (onProgress) {
                const latestLog = statusData.log || statusData.logsHistory?.slice(-1)[0] || 'Parameterizing...';
                onProgress(statusData.progress || 10, latestLog, statusData.logsHistory || []);
            }

            if (statusData.status === 'completed') {
                apiResult = statusData.result;
                break;
            } else if (statusData.status === 'failed' || statusData.status === 'cancelled') {
                throw new Error(statusData.log || 'Neural encoding task stopped.');
            }
        }

        return {
            fileName: originalName,
            status: 'completed',
            manifest: apiResult
        };
    }

    /**
     * Encodes folder bundle with multiple sub-files sequentially.
     */
    async compressFolderBundle(fileItems, targetDir, folderName, taskId = null, onProgress = null, precisionMode = 'fp16', computeDevice = 'cpu', parallelEnabled = true) {
        const activeTaskId = taskId || ('bundle_' + Date.now());
        const totalFiles = fileItems.length;

        for (let i = 0; i < totalFiles; i++) {
            const item = fileItems[i];
            if (!fs.existsSync(item.tempFilePath)) {
                console.warn(`[SDK Bundle Warning] Skipping missing file: ${item.tempFilePath}`);
                continue;
            }

            const subTaskId = `${activeTaskId}_file_${i}`;
            const fileProgress = Math.round(((i + 1) / totalFiles) * 100);

            await this.compressFile(
                item.tempFilePath,
                targetDir,
                item.originalName,
                subTaskId,
                (pct, log) => {
                    if (onProgress) {
                        onProgress(fileProgress, `[Bundle ${i + 1}/${totalFiles}] ${log}`);
                    }
                },
                precisionMode,
                computeDevice,
                parallelEnabled
            );
        }

        return {
            folderName,
            status: 'completed'
        };
    }

    /**
     * Decompresses container and requests PCM resynthesis from NeuraFS FastAPI engine.
     */
    async decompressToBuffer(hcsFilePath, targetSubPath = null) {
        let absPath = hcsFilePath;
        if (!fs.existsSync(absPath) && fs.existsSync(absPath + '.hcs')) {
            absPath += '.hcs';
        }

        if (!fs.existsSync(absPath)) {
            throw new Error(`Target HCS file not found: ${hcsFilePath}`);
        }

        const fileBuffer = fs.readFileSync(absPath);
        const { manifest, rawBlobs } = unpackHcsBuffer(fileBuffer);
        const originalInfo = manifest.original || {};
        const fileType = originalInfo.type || 'neural_media';

        if (fileType === 'neural_media') {
            const chunkUnits = manifest.chunks || [];
            const apiChunks = chunkUnits.map(unit => ({
                time_slice_idx: unit.time_slice_idx || 0,
                subband_idx: unit.subband_idx || 0,
                ch_idx: unit.ch_idx || 0,
                num_samples: unit.num_samples || 0,
                hidden_dim: unit.hidden_dim || 32,
                weights_b64: rawBlobs.subarray(unit.offset, unit.offset + unit.length).toString('base64')
            }));

            const response = await fetch(`${this.apiBaseUrl}/api/v1/resynthesize-neural-media`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chunks: apiChunks,
                    precision: manifest.neural?.precision || 'fp16'
                })
            });

            if (!response.ok) {
                throw new Error(`Resynthesis API failed: ${response.statusText}`);
            }

            const result = await response.json();
            const rawPcmBuffer = Buffer.from(result.pcm_b64, 'base64');
            const wavHeader = this.createWavHeader(
                rawPcmBuffer.length,
                originalInfo.sample_rate || 44100,
                originalInfo.channels || 2,
                result.bits_per_sample || 16,
                result.audio_format || 1
            );

            return {
                buffer: Buffer.concat([wavHeader, rawPcmBuffer]),
                originalName: originalInfo.name || 'audio.wav',
                fileType: 'media'
            };
        } else {
            return {
                buffer: rawBlobs,
                originalName: originalInfo.name || 'file.bin',
                fileType: 'binary'
            };
        }
    }

    /**
     * Constructs a standard 44-byte RIFF WAV header for PCM resynthesis.
     */
    createWavHeader(dataLength, sampleRate = 44100, channels = 2, bitsPerSample = 16, audioFormat = 1) {
        const byteRate = (sampleRate * channels * bitsPerSample) / 8;
        const blockAlign = (channels * bitsPerSample) / 8;
        const buffer = Buffer.alloc(44);

        buffer.write('RIFF', 0);
        buffer.writeUInt32LE(36 + dataLength, 4);
        buffer.write('WAVE', 8);
        buffer.write('fmt ', 12);
        buffer.writeUInt32LE(16, 16);
        buffer.writeUInt16LE(audioFormat, 20);
        buffer.writeUInt16LE(channels, 22);
        buffer.writeUInt32LE(sampleRate, 24);
        buffer.writeUInt32LE(byteRate, 28);
        buffer.writeUInt16LE(blockAlign, 32);
        buffer.writeUInt16LE(bitsPerSample, 34);
        buffer.write('data', 36);
        buffer.writeUInt32LE(dataLength, 40);

        return buffer;
    }
}

module.exports = NeuraFSSDK;