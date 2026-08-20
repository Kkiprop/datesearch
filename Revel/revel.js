const fs = require("fs");
const path = require("path");
const axios = require("axios");

// ======================================================
// FETCH SALES SUMMARY
// ======================================================

async function fetchSalesSummary(dateStr) {

    try {

        // Load credentials
        const credsPath = path.join(
            __dirname,
            "json_creds",
            "revel_creds.json"
        );

        const apiDetails = JSON.parse(
            fs.readFileSync(credsPath, "utf8")
        );

        // Final output object
        const allResults = {};

        for (const api of apiDetails) {

            const baseUrl = api.base_url;

            for (const establishment of api.establishments) {

                const establishmentName =
                    `${baseUrl.split(".")[0].split("//")[1]}${establishment}`;

                console.log("\n================================================");
                console.log(`Fetching ${establishmentName} for ${dateStr}`);
                console.log("================================================");

                const url =
                    `${baseUrl}reports/sales_summary/json/`;

                const params = {
                    posstation: "",
                    employee: "",
                    show_unpaid: 1,
                    show_irregular: 1,
                    range_from: `${dateStr} 00:00`,
                    range_to: `${dateStr} 23:59`,
                    establishment,
                    format: "json"
                };

                const headers = {
                    "API-AUTHENTICATION": api.api_auth_key,
                    "API-AUTHENTICATION-SECRET": api.api_auth_secret,
                    "Accept": "application/json"
                };

                try {

                    const response = await axios.get(url, {
                        headers,
                        params,
                        timeout: 60000
                    });

                    console.log("✅ Data retrieved");

                    const data = response.data;

                    const record =
                        Array.isArray(data) && data.length > 0
                            ? data[0]
                            : {};

                    const salesAmount =
                        parseFloat(record.total_sales || 0);

                    const customerCount =
                        record.total_orders || 0;

                    const totalDiscounts =
                        parseFloat(record.total_discounts || 0);

                    const refundsTotal =
                        parseFloat(record.refunds_total || 0);

                    const voidedTotal =
                        parseFloat(record.voided_total || 0);

                    const returnedTotal =
                        parseFloat(record.returned_total || 0);

                    let netSales =
                        salesAmount -
                        (
                            totalDiscounts +
                            refundsTotal +
                            voidedTotal +
                            returnedTotal
                        );

                    netSales = Number(netSales.toFixed(2));

                    const salesData = {
                        sales_amount: salesAmount,
                        customer_count: customerCount,
                        total_discounts: totalDiscounts,
                        refunds_total: refundsTotal,
                        voided_total: voidedTotal,
                        returned_total: returnedTotal,
                        net_sales: netSales
                    };

                    // Create date object if missing
                    if (!allResults[dateStr]) {
                        allResults[dateStr] = {};
                    }

                    // Save establishment data
                    allResults[dateStr][establishmentName] =
                        salesData;

                } catch (error) {

                    console.error(
                        `❌ Failed for ${establishmentName}`
                    );

                    console.error(
                        error.response?.status ||
                        error.message
                    );

                    console.error(
                        error.response?.data || ""
                    );
                }
            }
        }

        // ======================================================
        // SAVE JSON
        // ======================================================

        const outputDir = path.join(
            __dirname,
            "sales_summary"
        );

        const outputFile = path.join(
            outputDir,
            "sales_summary.json"
        );

        // Ensure directory exists
        if (!fs.existsSync(outputDir)) {
            fs.mkdirSync(outputDir, {
                recursive: true
            });
        }

        let existingData = {};

        // Load existing JSON if available
        if (fs.existsSync(outputFile)) {

            try {

                existingData = JSON.parse(
                    fs.readFileSync(outputFile, "utf8")
                );

            } catch {

                existingData = {};
            }
        }

        // Merge new data
        existingData = {
            ...existingData,
            ...allResults
        };

        // Save final JSON
        fs.writeFileSync(
            outputFile,
            JSON.stringify(existingData, null, 4)
        );

        console.log("\n💾 Data saved successfully");
        console.log(`📁 ${outputFile}`);

    } catch (error) {

        console.error(
            "❌ Fatal error:",
            error.message
        );
    }
}

// ======================================================
// MAIN
// ======================================================

async function main() {

    // Yesterday
    const today = new Date();

    today.setDate(today.getDate() - 1);

    const dateStr =
        today.toISOString().split("T")[0];

    console.log(`\n🚀 Processing ${dateStr}`);

    await fetchSalesSummary(dateStr);

    console.log("\n✅ Finished");
}

main();