const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const path = require("path");
const fs = require("fs");

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    backgroundColor: "#0a0908",
    titleBarStyle: "hidden",
    titleBarOverlay: {
      color: "#0a0908",
      symbolColor: "#c9a227",
      height: 36,
    },
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "..", "public", "index.html"));

  if (process.argv.includes("--dev")) {
    mainWindow.webContents.openDevTools();
  }
}

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

// ─── IPC HANDLERS ───────────────────────────────────────────────────────────

ipcMain.handle("open-pdf", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Select Rulebook PDF",
    filters: [{ name: "PDF Files", extensions: ["pdf"] }],
    properties: ["openFile"],
  });

  if (result.canceled || result.filePaths.length === 0) return null;

  const filePath = result.filePaths[0];
  const buffer = fs.readFileSync(filePath);
  return {
    name: path.basename(filePath),
    path: filePath,
    data: Array.from(new Uint8Array(buffer)),
  };
});

ipcMain.handle("save-json", async (event, { defaultName, jsonString }) => {
  const result = await dialog.showSaveDialog(mainWindow, {
    title: "Export Extraction Data",
    defaultPath: defaultName,
    filters: [{ name: "JSON Files", extensions: ["json"] }],
  });

  if (result.canceled) return false;
  fs.writeFileSync(result.filePath, jsonString, "utf-8");
  return true;
});

// Resolve the path to pdfjs-dist worker for the renderer
ipcMain.handle("get-pdfjs-worker-path", () => {
  try {
    const workerPath = require.resolve("pdfjs-dist/build/pdf.worker.mjs");
    return workerPath;
  } catch {
    try {
      const workerPath = require.resolve("pdfjs-dist/build/pdf.worker.js");
      return workerPath;
    } catch {
      return null;
    }
  }
});