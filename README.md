# GameForge Extractor

Desktop application for extracting structured data from rulebook PDFs.  
Built with Electron. Designed by b1tr0n1n.

## What It Does

- Ingests any rulebook PDF
- Extracts text and detects section hierarchy
- Classifies blocks: headings, subheadings, body, notes
- Identifies cross-references between rules
- Exports structured JSON for downstream processing

## Setup

```bash
# Clone or copy the project folder, then:
cd gameforge-extractor

# Install dependencies
npm install

# Run in development mode
npm start

# Run with DevTools open
npx electron . --dev
```

## Build Executable

```bash
# Windows (.exe installer)
npm run build

# macOS (.dmg)
npm run build:mac

# Linux (.AppImage)
npm run build:linux
```

Built executables appear in the `dist/` folder.

## Project Structure

```
gameforge-extractor/
├── package.json          # Dependencies & build config
├── src/
│   ├── main.js           # Electron main process (window, file dialogs, IPC)
│   └── preload.js        # Secure bridge between main & renderer
├── public/
│   └── index.html        # UI + extraction engine (single file)
└── dist/                 # Build output (generated)
```

## Requirements

- Node.js 18+
- npm

## Adding an Icon

Place your icon files in `public/`:
- `icon.ico` (Windows)
- `icon.icns` (macOS)
- `icon.png` (Linux, 512x512)

## Next Steps

This is Layer 1 of the GameForge pipeline:
1. **PDF Extraction** ← you are here
2. **LLM Decomposition** — feed extracted JSON to Claude API for rule parsing
3. **Schema Normalization** — map game-specific rules to universal taxonomy
4. **API** — serve structured rules via REST endpoints
5. **GameForge Engine** — React UI consumes API, generates trackers
