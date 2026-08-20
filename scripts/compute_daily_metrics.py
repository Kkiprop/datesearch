import json
import sys
from pathlib import Path
from datetime import datetime
import uuid


def load_json(path):
    if not Path(path).exists():
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_order_counts(rec):
    # try common keys used in provided files
    for k in ('order_counts', 'customer_count', 'customer_count_data', 'customer_count_data'):
        v = rec.get(k)
        if isinstance(v, dict):
            return v
    # sometimes order_counts is nested or missing
    return {}


def main(
    sales_path='Dashboard_data.store_wise_sales.json',
    payroll_path='Payroll_dashboard.Payroll_daily.json',
    waste_path='Dashboard_data.waste_tool.json',
    gross_path='Dashboard_data.gross_margin.json',
    customer_path='Dashboard_data.customer_count.json',
    out_path='daily_metrics.json',
):
    sales = load_json(sales_path)
    payroll = load_json(payroll_path)
    waste = load_json(waste_path)
    gross = load_json(gross_path)
    customer = load_json(customer_path)

    # index by date
    sales_by_date = {r.get('date'): r.get('sales_data', {}) for r in sales}
    payroll_by_date = {r.get('date'): r.get('payroll_data', {}) for r in payroll}
    waste_by_date = {r.get('date'): r.get('total_waste_per_store', {}) for r in waste}
    gross_by_date = {r.get('date'): r.get('stores', {}) for r in gross}
    cust_by_date = {r.get('date'): extract_order_counts(r) for r in customer}

    all_dates = sorted(set(list(sales_by_date) + list(payroll_by_date) + list(waste_by_date) + list(gross_by_date) + list(cust_by_date)))

    results = []
    for date in all_dates:
        sales_data = sales_by_date.get(date, {}) or {}
        payroll_data = payroll_by_date.get(date, {}) or {}
        waste_data = waste_by_date.get(date, {}) or {}
        gross_data = gross_by_date.get(date, {}) or {}
        cust_data = cust_by_date.get(date, {}) or {}

        stores = set()
        stores.update(sales_data.keys())
        stores.update(payroll_data.keys())
        stores.update(waste_data.keys())
        stores.update(gross_data.keys())
        stores.update(cust_data.keys())

        data_section = {}
        for store in sorted(stores):
            # net_sales from sales_data
            net_sales = 0.0
            srec = sales_data.get(store)
            if isinstance(srec, dict):
                net_sales = srec.get('net_sales', 0.0) or 0.0

            total_waste = waste_data.get(store, 0.0) or 0.0

            net_revenue = net_sales - total_waste

            payroll_val = payroll_data.get(store, 0.0) or 0.0
            # payroll entries may be None
            if payroll_val is None:
                payroll_val = 0.0

            net_revenue_payroll_adjusted = net_revenue - payroll_val

            g = gross_data.get(store, {}) or {}
            total_revenue = g.get('total_revenue') or 0.0
            total_cost = g.get('total_cost') or 0.0
            gross_margin_percent = g.get('gross_margin_percent')
            if gross_margin_percent is None:
                # compute if possible
                if total_revenue:
                    gross_margin_percent = (total_revenue - total_cost) / total_revenue * 100
                else:
                    gross_margin_percent = None

            # GM% payroll adjusted
            gm_payroll_adj = None
            if total_revenue:
                gm_payroll_adj = (total_revenue - total_cost - payroll_val) / total_revenue * 100

            # order counts
            orders = cust_data.get(store)
            try:
                orders = int(orders) if orders is not None else 0
            except Exception:
                orders = 0

            avg_basket = None
            if orders:
                avg_basket = net_revenue / orders

            # round/keep floats consistent
            entry = {
                'Net_Revenue': round(net_revenue, 2),
                'Net_Revenue_payroll_Adjusted': round(net_revenue_payroll_adjusted, 2),
                'GM%': round(gross_margin_percent, 2) if gross_margin_percent is not None else None,
                'GM%_Payroll_Adjusted': round(gm_payroll_adj, 2) if gm_payroll_adj is not None else None,
                'Average_Basket': round(avg_basket, 2) if avg_basket is not None else None,
            }
            data_section[store] = entry

        out_rec = {
            '_id': {'$oid': uuid.uuid4().hex[:24]},
            'date': date,
            'data': data_section,
            'updated_at': {'$date': datetime.utcnow().isoformat() + 'Z'},
        }
        results.append(out_rec)

    # write output
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    print(f'Wrote {len(results)} date records to {out_path}')


if __name__ == '__main__':
    args = sys.argv[1:]
    kwargs = {}
    if args:
        # allow specifying output path as first arg
        kwargs['out_path'] = args[0]
    main(**kwargs)
