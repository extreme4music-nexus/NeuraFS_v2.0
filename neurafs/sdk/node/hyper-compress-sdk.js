/**
 * NeuraFS Node.js Software Development Kit (SDK)
 * Handles 12-byte HCS container unpacking, manifest inspection, and RAM resynthesis.
 */

const fs = require('fs');
const path = require('path');
const lzma = require('lzma-native');

/**
 * Unpacks and parses raw .hcs binary buffer based on 12-byte header spec.
 * Header: Magic (4B) | Flags (4B) | Manifest Length UInt32BE (4B)
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
     * @param {string} apiBaseUrl - Base HTTP URL for NeuraFS FastAPI backend
     */
    constructor(apiBaseUrl = 'http://localhost:8000') {
        this.apiBaseUrl = apiBaseUrl;
    }

    /**
     * Reads and parses metadata manifest from .hcs container without decompressing weight blobs.
     * @param {string} hcsFilePath - Path to target .hcs file
     * @returns {Object} Extensible metadata manifest
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
     * Decompresses container and requests PCM resynthesis from the API engine.
     * @param {string} hcsFilePath - Path to target .hcs file
     * @returns {Promise<{buffer: Buffer, originalName: string, fileType: string}>}
     */
    async decompressToBuffer(hcsFilePath) {
        if (!fs.existsSync(hcsFilePath)) {
            throw new Error(`Target HCS file not found: ${hcsFilePath}`);
        }

        const fileBuffer = fs.readFileSync(hcsFilePath);
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