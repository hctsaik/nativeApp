const e = require('electron')
console.log('process.type:', process.type)
console.log('electron type:', typeof e)
if (typeof e === 'object' && e !== null) {
  console.log('has ipcMain:', 'ipcMain' in e)
  console.log('SUCCESS - APIs accessible!')
  if (e.app) e.app.quit()
} else {
  console.log('FAIL - still getting path string')
  process.exit(0)
}
