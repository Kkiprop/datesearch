import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const SCRIPT_DIR = path.dirname(__filename);
const OUTPUT_DIR = path.join(SCRIPT_DIR, "revel_exports");
const OUTPUT_FILE = path.join(OUTPUT_DIR, "revel_sales_customer_first_101.json");
const POLL_INTERVAL_SECONDS = Number.parseInt(process.env.REVEL_POLL_INTERVAL_SECONDS || "60", 10);
const STORE_NAME_MAPPING = {
    apnabazar1: "Sunnyvale",
    apnabazar2: "Fremont",
    stopandshopca1: "Karthik",
    stopandshopca2: "Milpitas"
};
const FIELD_NAMES = [
    "sales_amount",
    "customer_count",
    "total_discounts",
    "refunds_total",
    "voided_total",
    "returned_total",
    "net_sales"
];


function resolveCredsPath() {
    const candidatePaths = [
        path.join(SCRIPT_DIR, "json_creds", "revel_creds.json"),
        path.join(process.cwd(), "Revel", "json_creds", "revel_creds.json"),
        path.join(process.cwd(), "json_creds", "revel_creds.json")
    ];

    for (const candidatePath of candidatePaths) {
        if (fs.existsSync(candidatePath)) {
            return candidatePath;
        }
    }

    throw new Error("Could not find revel_creds.json");
}


function loadRevelCredentials() {
    const credsPath = resolveCredsPath();
    return JSON.parse(fs.readFileSync(credsPath, "utf8"));
}


function buildRevelUrl(baseUrl, endpointPath) {
    let normalizedBaseUrl = baseUrl.replace(/\/+$/, "");
    if (normalizedBaseUrl.endsWith("/reports")) {
        normalizedBaseUrl = normalizedBaseUrl.slice(0, -"/reports".length);
    }

    return `${normalizedBaseUrl}/${endpointPath.replace(/^\/+/, "")}`;
}


function toSalesCustomerRecord(record) {
    const salesAmount = Number.parseFloat(record.total_sales || 0) || 0;
    const customerCount = Number.parseInt(record.total_orders || 0, 10) || 0;
    const totalDiscounts = Number.parseFloat(record.total_discounts || 0) || 0;
    const refundsTotal = Number.parseFloat(record.refunds_total || 0) || 0;
    const voidedTotal = Number.parseFloat(record.voided_total || 0) || 0;
    const returnedTotal = Number.parseFloat(record.returned_total || 0) || 0;
    const netSales = salesAmount - (totalDiscounts + refundsTotal + voidedTotal + returnedTotal);

    return {
        sales_amount: Number(salesAmount.toFixed(2)),
        customer_count: customerCount,
        total_discounts: Number(totalDiscounts.toFixed(2)),
        refunds_total: Number(refundsTotal.toFixed(2)),
        voided_total: Number(voidedTotal.toFixed(2)),
        returned_total: Number(returnedTotal.toFixed(2)),
        net_sales: Number(netSales.toFixed(2))
    };
}


function saveExport(dateStr, exportData) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });

    const payload = {
        generated_at: new Date().toISOString(),
        date: dateStr,
        fields: FIELD_NAMES,
        data: exportData
    };

    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(payload, null, 4));
    return OUTPUT_FILE;
}


async function fetchSalesSummary(dateStr) {
    const apiDetails = loadRevelCredentials();
    const exportData = {};

    for (const api of apiDetails) {
        const baseUrl = api.base_url;
        const authHeader = `${api.api_auth_key}:${api.api_auth_secret}`;

        for (const establishment of api.establishments) {
            const revelEstablishmentName = `${baseUrl.split(".")[0].split("//")[1]}${establishment}`;
            const establishmentName = STORE_NAME_MAPPING[revelEstablishmentName] || revelEstablishmentName;

            console.log();
            console.log(`Fetching data for ${establishmentName} on ${dateStr}...`);

            const url = new URL(buildRevelUrl(baseUrl, "reports/sales_summary/json/"));
            url.search = new URLSearchParams({
                posstation: "",
                employee: "",
                show_unpaid: "1",
                show_irregular: "1",
                range_from: `${dateStr} 00:00`,
                range_to: `${dateStr} 23:59`,
                establishment: String(establishment),
                format: "json"
            }).toString();

            const response = await fetch(url, {
                method: "GET",
                headers: {
                    "API-AUTHENTICATION": authHeader,
                    "Accept": "application/json"
                }
            });

            if (!response.ok) {
                const responseText = await response.text();
                console.log(`❌ Failed to fetch data. HTTP ${response.status}: ${responseText}`);
                exportData[establishmentName] = {
                    item_count: 0,
                    items: []
                };
                continue;
            }

            console.log("✅ Data retrieved successfully!");
            const responseData = await response.json();
            let sourceItems = [];

            if (Array.isArray(responseData)) {
                sourceItems = responseData.slice(0, 100);
            } else if (responseData) {
                sourceItems = [responseData];
            }

            const filteredItems = sourceItems.map(toSalesCustomerRecord);
            exportData[establishmentName] = {
                item_count: filteredItems.length,
                items: filteredItems
            };
            console.log(`💾 Prepared ${filteredItems.length} filtered items for ${establishmentName}`);
        }
    }

    const outputPath = saveExport(dateStr, exportData);
    console.log(`💾 Saved Revel export → ${outputPath}`);
    return outputPath;
}


function getTargetDate() {
    const targetDate = process.env.REVEL_TARGET_DATE;
    if (targetDate) {
        return targetDate;
    }

    const useYesterday = (process.env.REVEL_USE_YESTERDAY || "false").toLowerCase() === "true";
    const baseDate = new Date();
    if (useYesterday) {
        baseDate.setDate(baseDate.getDate() - 1);
    }

    return baseDate.toISOString().split("T")[0];
}


async function runOnce() {
    const dateStr = getTargetDate();

    console.log();
    console.log(`Processing date: ${dateStr}`);
    console.log("=".repeat(70));
    console.log(`⏳ Fetching first 100 filtered sales summary items for ${dateStr}`);
    console.log("=".repeat(70));

    try {
        await fetchSalesSummary(dateStr);
        console.log("✅ Revel export completed.");
    } catch (error) {
        console.log(`❌ Error occurred: ${error.message}`);
    }
}


async function runContinuously() {
    console.log(`▶ Continuous polling enabled. Interval: ${POLL_INTERVAL_SECONDS} seconds`);

    while (true) {
        await runOnce();
        console.log(`⏲ Waiting ${POLL_INTERVAL_SECONDS} seconds before next fetch...`);
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_SECONDS * 1000));
    }
}


async function main() {
    const continuousMode = (process.env.REVEL_CONTINUOUS || "true").toLowerCase() === "true";
    if (continuousMode) {
        await runContinuously();
        return;
    }

    await runOnce();
}


main();