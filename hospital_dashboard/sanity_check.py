import sys, time
sys.path.insert(0, '.')

print('=' * 50)
print('HOSPITAL DASHBOARD SANITY CHECK')
print('=' * 50)

results = []

def check(name, fn):
    try:
        t0 = time.time()
        val = fn()
        ms = (time.time() - t0) * 1000
        results.append(('PASS', name, ms, None))
        print(f'  PASS  {name} ({ms:.0f}ms)')
        return val
    except Exception as e:
        results.append(('FAIL', name, 0, str(e)))
        print(f'  FAIL  {name} -> {e}')
        return None

print()
print('--- 1. DATABASE CONNECTIONS ---')
from database_connection import get_patients, get_admissions, get_icu_beds

patients   = check('get_patients',   get_patients)
admissions = check('get_admissions', get_admissions)
icu        = check('get_icu_beds',   get_icu_beds)

print()
print('--- 2. ROW COUNTS ---')
if patients   is not None: print(f'  patients:   {len(patients)} rows')
if admissions is not None: print(f'  admissions: {len(admissions)} rows')
if icu        is not None: print(f'  icu_beds:   {len(icu)} rows')

print()
print('--- 3. ANALYTICS FUNCTIONS ---')
from hospital_analytics import (
    get_system_strain,
    get_high_readmission_patients,
    get_likely_no_shows,
    get_admissions_trend,
    get_department_no_show_rates,
)

strain   = check('get_system_strain',             get_system_strain)
highrisk = check('get_high_readmission_patients', lambda: get_high_readmission_patients(limit=20))
noshows  = check('get_likely_no_shows',           lambda: get_likely_no_shows(days_ahead=1))
trend    = check('get_admissions_trend',          lambda: get_admissions_trend(days=30))
deptns   = check('get_department_no_show_rates',  get_department_no_show_rates)

print()
print('--- 4. DATA QUALITY CHECKS ---')

if strain:
    required = [
        'icu_rate', 'readmit_rate', 'noshow_rate', 'strain_score',
        'strain_level', 'total_patients', 'icu_total', 'icu_occupied',
        'high_readmission_count', 'data_as_of'
    ]
    missing = [k for k in required if k not in strain]
    if missing:
        print(f'  WARN  strain dict missing keys: {missing}')
    else:
        print(f'  PASS  strain dict has all required keys')
    print(f'  INFO  data_as_of:             {strain.get("data_as_of", "NOT SET")}')
    print(f'  INFO  strain_level:           {strain.get("strain_level")}')
    print(f'  INFO  strain_score:           {strain.get("strain_score")}')
    print(f'  INFO  icu_occupied:           {strain.get("icu_occupied")} / {strain.get("icu_total")}')
    print(f'  INFO  high_readmission_count: {strain.get("high_readmission_count")}')
    print(f'  INFO  admissions_today:       {strain.get("admissions_today")}')
    print(f'  INFO  discharges_today:       {strain.get("discharges_today")}')

if highrisk is not None and not highrisk.empty:
    if 'readmission_risk' in highrisk.columns:
        mn = highrisk['readmission_risk'].min()
        mx = highrisk['readmission_risk'].max()
        if mx > 1.0:
            print(f'  WARN  readmission_risk max={mx:.1f} -- should be 0-1 not 0-100')
        else:
            print(f'  PASS  readmission_risk range: {mn:.2f} - {mx:.2f}')
    unique_pts = highrisk['patient_id'].nunique()
    print(f'  INFO  high risk rows={len(highrisk)} unique_patients={unique_pts}')
    if len(highrisk) != unique_pts:
        print(f'  WARN  duplicate patient rows detected ({len(highrisk)} rows vs {unique_pts} unique)')

if trend is not None:
    print(f'  INFO  admissions trend: {len(trend)} rows')
    if len(trend) == 0:
        print(f'  WARN  trend is empty -- date filter may still be broken')
    else:
        print(f'  INFO  trend date range: {trend["date"].min()} to {trend["date"].max()}')
        cols = list(trend.columns)
        print(f'  INFO  trend columns: {cols}')

if noshows is not None:
    print(f'  INFO  no-shows: {len(noshows)} rows')
    if len(noshows) == 0:
        print(f'  WARN  no-shows empty -- check date fix or no_show column')
    else:
        print(f'  INFO  no-show columns: {list(noshows.columns)}')

if deptns is not None and not deptns.empty:
    print(f'  INFO  dept no-show rows: {len(deptns)}')
    top = deptns.iloc[0]
    print(f'  INFO  highest no-show dept: {top["department"]} at {top["no_show_rate"]*100:.1f}%')

print()
print('--- 5. AI AGENT ---')
from hospital_ai_agent import generate_operational_summary, answer_user_question

if strain:
    ai_summary = check('generate_operational_summary',
                       lambda: generate_operational_summary(strain))
    if ai_summary:
        preview = ai_summary[:100].replace('\n', ' ')
        print(f'  INFO  preview: "{preview}..."')

    ai_answer = check('answer_user_question',
                      lambda: answer_user_question(
                          'How many ICU beds are occupied?', strain))
    if ai_answer:
        preview = ai_answer[:100].replace('\n', ' ')
        print(f'  INFO  preview: "{preview}..."')

print()
print('--- 6. CACHE ---')
try:
    from database_connection import DATA_CACHE
    t0 = time.time()
    DATA_CACHE.warm()
    ms = (time.time() - t0) * 1000
    print(f'  PASS  cache warm completed in {ms:.0f}ms')
    t0 = time.time()
    get_patients()
    ms2 = (time.time() - t0) * 1000
    if ms2 < 10:
        print(f'  PASS  cached fetch: {ms2:.1f}ms (cache working)')
    else:
        print(f'  WARN  cached fetch: {ms2:.1f}ms (expected <10ms)')
except ImportError:
    print(f'  SKIP  DATA_CACHE not implemented yet')
except Exception as e:
    print(f'  FAIL  cache error: {e}')

print()
print('=' * 50)
passed = sum(1 for r in results if r[0] == 'PASS')
failed = sum(1 for r in results if r[0] == 'FAIL')
total_ms = sum(r[2] for r in results)
print(f'RESULT: {passed} passed  {failed} failed  {total_ms:.0f}ms total')
if failed == 0:
    print('ALL CHECKS PASSED -- dashboard should work correctly')
else:
    print('FAILURES:')
    for r in results:
        if r[0] == 'FAIL':
            print(f'  {r[1]}: {r[3]}')
print('=' * 50)