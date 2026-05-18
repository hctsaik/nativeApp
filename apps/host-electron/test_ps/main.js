const e = require('electron')
console.log('process.type:', process.type)
console.log('electron type:', typeof e)
if (typeof e === 'object' && e !== null) {
  console.log('has ipcMain:', 'ipcMain' in e)
  console.log('keys:', Object.keys(e).slice(0,10).join(', '))
  if (e.app) e.app.quit()
} else {
  console.log('value:', String(e).slice(0, 100))
  process.exit(0)
}
