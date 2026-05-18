const fs = require('fs')
const path = require('path')
const logFile = path.join(__dirname, 'output.txt')

try {
  const e = require('electron')
  fs.writeFileSync(logFile, 'process.type: ' + process.type + '\n')
  fs.appendFileSync(logFile, 'electron type: ' + (typeof e) + '\n')
  if (typeof e === 'object' && e !== null) {
    fs.appendFileSync(logFile, 'has ipcMain: ' + ('ipcMain' in e) + '\n')
    fs.appendFileSync(logFile, 'SUCCESS\n')
    if (e.app) {
      e.app.whenReady().then(() => { e.app.quit() })
    }
  } else {
    fs.appendFileSync(logFile, 'value: ' + String(e).slice(0, 80) + '\n')
    fs.appendFileSync(logFile, 'FAIL\n')
  }
} catch(err) {
  fs.writeFileSync(logFile, 'ERROR: ' + err.message + '\n' + err.stack)
}
