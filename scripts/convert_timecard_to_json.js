const xlsx = require('xlsx');
const fs = require('fs');

const excelFile = 'Timecard Fremont.xlsx';
const workbook = xlsx.readFile(excelFile);
const sheetName = workbook.SheetNames[0];
const sheet = workbook.Sheets[sheetName];
const data = xlsx.utils.sheet_to_json(sheet);

// Example columns: Date, Employee Name, Regular, Overtime
// Adjust column names if needed
const grouped = {};
data.forEach(row => {
  const date = String(row['Date']);
  const emp = row['Employee Name'];
  const regular = row['Regular'];
  const overtime = row['Overtime'];
  if (!grouped[date]) grouped[date] = {};
  grouped[date][emp] = {
    Regular: regular,
    Overtime: overtime
  };
});

fs.writeFileSync('timecard_fremont_by_date.json', JSON.stringify(grouped, null, 2));
console.log('Conversion complete. Output: timecard_fremont_by_date.json');
