const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("gameforge", {
  openPDF: () => ipcRenderer.invoke("open-pdf"),
  saveJSON: (defaultName, jsonString) =>
    ipcRenderer.invoke("save-json", { defaultName, jsonString }),
  getWorkerPath: () => ipcRenderer.invoke("get-pdfjs-worker-path"),
});