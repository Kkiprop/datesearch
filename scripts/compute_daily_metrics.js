const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function loadJson(p) {
  try {
    const full = path.resolve(p);
    if (!fs.existsSync(full)) return [];
    return JSON.parse(fs.readFileSync(full, 'utf8'));
  } catch (e) {
    console.error('Error loading', p, e.message);
    return [];
  }
}

function extractOrderCounts(rec) {
  for (const k of ['order_counts', 'customer_count', 'customer_count_data']) {
    if (rec && Object.prototype.hasOwnProperty.call(rec, k)) {
      const v = rec[k];
      if (v && typeof v === 'object') return v;
    }
  }
  return {};
}

function numberOrZero(v) {
  if (v === null || v === undefined) return 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function buildIndex(arr, keyExtractor) {
  const out = Object.create(null);
  for (const r of arr || []) {
    const d = r && r.date;
    if (!d) continue;
    out[d] = keyExtractor ? keyExtractor(r) : r;
  }
  return out;
}

function main(options = {}) {
  const sales = loadJson(options.sales || 'Dashboard_data.store_wise_sales.json');
  const payroll = loadJson(options.payroll || 'Payroll_dashboard.Payroll_daily.json');
  const waste = loadJson(options.waste || 'Dashboard_data.waste_tool.json');
  const gross = loadJson(options.gross || 'Dashboard_data.gross_margin.json');
  const customer = loadJson(options.customer || 'Dashboard_data.customer_count.json');

  const salesByDate = buildIndex(sales, r => r.sales_data || {});
  const payrollByDate = buildIndex(payroll, r => r.payroll_data || {});
  const wasteByDate = buildIndex(waste, r => r.total_waste_per_store || {});
  const grossByDate = buildIndex(gross, r => r.stores || {});
  const custByDate = buildIndex(customer, r => extractOrderCounts(r));

  const allDates = Array.from(new Set([
    ...Object.keys(salesByDate),
    ...Object.keys(payrollByDate),
    ...Object.keys(wasteByDate),
    ...Object.keys(grossByDate),
    ...Object.keys(custByDate),
  ])).sort();

  const results = [];

  for (const date of allDates) {
    const sdata = salesByDate[date] || {};
    const pdata = payrollByDate[date] || {};
    const wdata = wasteByDate[date] || {};
    const gdata = grossByDate[date] || {};
    const cdata = custByDate[date] || {};

    const stores = new Set([
      ...Object.keys(sdata),
      ...Object.keys(pdata),
      ...Object.keys(wdata),
      ...Object.keys(gdata),
      ...Object.keys(cdata),
    ]);

    const dataSection = {};
    for (const store of Array.from(stores).sort()) {
      const srec = sdata[store] || {};
      const net_sales = numberOrZero(srec.net_sales);
      const total_waste = numberOrZero(wdata[store]);
      const net_revenue = net_sales - total_waste;

      let payrollVal = pdata[store];
      if (payrollVal === null || payrollVal === undefined) payrollVal = 0;
      payrollVal = numberOrZero(payrollVal);

      const net_revenue_payroll_adjusted = net_revenue - payrollVal;

      const g = gdata[store] || {};
      const total_revenue = numberOrZero(g.total_revenue);
      const total_cost = numberOrZero(g.total_cost);
      let gross_margin_percent = (g && g.gross_margin_percent !== undefined) ? g.gross_margin_percent : null;
      if ((gross_margin_percent === null || gross_margin_percent === undefined) && total_revenue) {
        gross_margin_percent = ((total_revenue - total_cost) / total_revenue) * 100;
      }

      let gm_payroll_adj = null;
      if (total_revenue) {
        gm_payroll_adj = ((total_revenue - total_cost - payrollVal) / total_revenue) * 100;
      }

      let orders = cdata[store];
      orders = numberOrZero(orders);

      let avg_basket = null;
      if (orders) avg_basket = net_revenue / orders;

      dataSection[store] = {
        Net_Revenue: Number(net_revenue.toFixed(2)),
        Net_Revenue_payroll_Adjusted: Number(net_revenue_payroll_adjusted.toFixed(2)),
        'GM%': (gross_margin_percent !== null && gross_margin_percent !== undefined) ? Number(gross_margin_percent.toFixed(2)) : null,
        'GM%_Payroll_Adjusted': (gm_payroll_adj !== null && gm_payroll_adj !== undefined) ? Number(gm_payroll_adj.toFixed(2)) : null,
        Average_Basket: (avg_basket !== null && avg_basket !== undefined) ? Number(avg_basket.toFixed(2)) : null,
      };
    }

    results.push({
      _id: { $oid: crypto.randomBytes(12).toString('hex') },
      date,
      data: dataSection,
      updated_at: { $date: new Date().toISOString() },
    });
  }

  const outPath = options.out || 'daily_metricsjs.json';
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
  console.log(`Wrote ${results.length} records to ${outPath}`);
}

if (require.main === module) {
  const out = process.argv[2];
  main({ out });
}
