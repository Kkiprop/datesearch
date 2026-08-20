const xlsx = require('xlsx');
const fs = require('fs');

function parseTimecard(inputFile, outputFile) {
    try {
        // 1. Load the workbook and get the first sheet
        const workbook = xlsx.readFile(inputFile);
        const sheetName = workbook.SheetNames[0];
        const sheet = workbook.Sheets[sheetName];

        // 2. Convert to a raw 2D array (range: 0 includes empty cells)
        const rows = xlsx.utils.sheet_to_json(sheet, { header: 1, defval: null });

        let dataTree = {};
        let currentEmployee = null;
        let lookingForEmployee = false;
        let collectingData = false;

        rows.forEach((row, index) => {
            // Clean the row: convert to lowercase strings for searching
            const rowStr = row.map(cell => String(cell || '').trim().toLowerCase());

            // A. TRIGGER: Found the Employee Header Row
            if (rowStr.includes("employee name") && rowStr.includes("pay period")) {
                lookingForEmployee = true;
                collectingData = false;
                return;
            }

            // B. ACTION: Pick the Employee Name (Row directly below header)
            if (lookingForEmployee) {
                // Pick from Column A (0) or B (1) depending on alignment
                currentEmployee = String(row[0] || row[1] || '').trim();
                lookingForEmployee = false;
                return;
            }

            // C. TRIGGER: Found the Data Header Row
            if (rowStr.includes("date") && rowStr.includes("regular")) {
                collectingData = true;
                return;
            }

            // D. ACTION: Collect Data Rows
            if (collectingData && currentEmployee) {
                const rawDate = row[0];
                
                // Stop if row is empty or contains "Total"
                if (!rawDate || String(rawDate).toLowerCase().includes('total')) {
                    collectingData = false;
                    return;
                }

                // Handle Excel Date Conversion
                let dateKey;
                if (typeof rawDate === 'number') {
                    // Excel stores dates as serial numbers
                    const dateObj = xlsx.utils.format_cell({ v: rawDate, t: 'd' });
                    dateKey = new Date(rawDate * 86400000 - 2209161600000).toISOString().split('T')[0];
                } else {
                    dateKey = String(rawDate).trim();
                }

                // Map Columns: Regular (Index 3), Overtime (Index 4)
                const regHours = row[3] || 0;
                const otHours = row[4] || 0;

                // Build the Tree: { Date: { Employee: { Regular, Overtime } } }
                if (!dataTree[dateKey]) {
                    dataTree[dateKey] = {};
                }

                dataTree[dateKey][currentEmployee] = {
                    "Regular": regHours,
                    "Overtime": otHours
                };
            }
        });

        // 3. Write to JSON file
        fs.writeFileSync(outputFile, JSON.stringify(dataTree, null, 4));
        console.log(`Successfully created ${outputFile}`);

    } catch (error) {
        console.error("An error occurred:", error.message);
    }
}

// Run the function
parseTimecard('Timecard Fremont.xlsx', 'timesheetjs.json');