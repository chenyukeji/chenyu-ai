import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/chenyu-kaifa/skills/chenyu-xuanpin/scripts'
sys.path.insert(0, str(SCRIPTS))
import run
import strategy_h
from strategy_evidence import analyze_evidence
from strategy_inputs import read_input
from sellersprite_h import _matches_month_query


def historical(asin='B0SEASON01', month='2025-10', **values):
    return {'marketplace':'US', 'asin':asin, 'history_month':month,
            'estimated_sales':600, 'sales_growth_percent':50,
            'source_ref':'https://www.sellersprite.com/v3/product-research?month='+month,
            'product_name':'Seasonal item', **values}


def test_month_window_rolls_over_year_and_rejects_invalid_options():
    assert strategy_h.target_months('2026-12-10', 2) == ['2025-12','2026-01','2026-02']
    assert strategy_h.target_months('2026-10-08', 3) == ['2025-10','2025-11','2025-12','2026-01']
    for invalid in (1, 4, '3', True):
        with pytest.raises(ValueError): strategy_h.target_months('2026-10-08', invalid)


def test_h_uses_monthly_sales_and_deduplicates_without_inventing_missing_months():
    rows=[historical(), historical(), historical(month='2025-11',estimated_sales=900),
          historical('B0SEASON02',month='2026-10'),
          historical('B0SEASON03',sales_growth_percent=None),
          historical('B0SEASON04',marketplace='DE'),
          historical('B0SEASON05',source_ref=None)]
    report=strategy_h.analyze_monthly_surge(rows,strategy_h.target_months('2026-10-08'),['US'])
    assert report['count']==1
    item=report['candidates'][0]
    assert item['hit_months']==2 and item['peak_sales']==900
    assert [x['month'] for x in item['monthly_evidence']]==['2025-10','2025-11']
    assert len(report['rejected'])==4
    assert '待跨年复核' in item['conclusion']


def test_import_excel_and_csv_preserve_explicit_month_context(tmp_path):
    csv=tmp_path/'history.csv'
    csv.write_text('ASIN,月销量,月销量增长率\nB0SEASON01,600,50%\n',encoding='utf-8-sig')
    content,_=read_input({'path':str(csv),'marketplace':'US','history_month':'2025-10'})
    assert content['records'][0]['history_month']=='2025-10'
    assert content['records'][0]['sales_growth_percent']=='50%'
    openpyxl=pytest.importorskip('openpyxl')
    wb=openpyxl.Workbook()
    wb.active.append(['ASIN','月销量','月销量增长率'])
    wb.active.append(['B0SEASON01',600,0.5])
    wb.active['C2'].number_format='0%'
    path=tmp_path/'history.xlsx'
    wb.save(path)
    content,_=read_input({'path':str(path),'marketplace':'US','history_month':'2025-10'})
    assert content['records'][0]['estimated_sales']==600
    assert content['records'][0]['sales_growth_percent']==50


def test_h_end_to_end_and_resume_keeps_selected_window(tmp_path, monkeypatch):
    monkeypatch.setattr(run, 'collect_monthly_surges', lambda p: (_ for _ in ()).throw(AssertionError('must not collect')))
    result=run.run_discovery_flow({'request':'历史季节性选品','run_dir':str(tmp_path),'as_of_date':'2026-10-08',
        'strategy_selection':{'strategy_ids':['H'],'source_marketplaces':['US'],'parameters':{'h_following_months':3}},
        'discovery':{'collect_live':False},'discovery_records':[historical(month='2026-01')]})
    assert result['status']=='PARTIAL'
    assert any('未覆盖' in warning for warning in result['warnings'])
    assert Path(result['workbook']['path']).is_file()
    report=json.loads((tmp_path/'09-screening.json').read_text())
    assert report['months'][-1]=='2026-01'
    assert report['candidates'][0]['monthly_evidence'][0]['month']=='2026-01'
    resumed=run.run_discovery_flow({'run_dir':str(tmp_path),'as_of_date':'2026-10-08','discovery':{'collect_live':False}})
    assert resumed['counts']['qualified']==1


def test_h_blocks_new_releases_database(tmp_path):
    with pytest.raises(ValueError, match='仅适用于 E'):
        run.run_discovery_flow({'request':'历史季节性选品','run_dir':str(tmp_path),
           'strategy_selection':{'strategy_ids':['H']},'discovery':{'source':'new_releases_db'}})


def test_live_partial_coverage_stays_partial_on_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(run, 'collect_monthly_surges', lambda p: {'collection_status':'partial','records':[historical()]})
    payload={'request':'历史季节性选品','run_dir':str(tmp_path),'as_of_date':'2026-10-08',
             'strategy_selection':{'strategy_ids':['H'],'source_marketplaces':['US']}}
    assert run.run_discovery_flow(payload)['status']=='PARTIAL'
    monkeypatch.setattr(run, 'collect_monthly_surges', lambda p: (_ for _ in ()).throw(AssertionError('cached')))
    assert run.run_discovery_flow({'run_dir':str(tmp_path),'as_of_date':'2026-10-08'})['status']=='PARTIAL'


def test_keyword_requires_mapping_and_does_not_invent_growth():
    row={**historical(), 'keyword':'winter decor','search_volume':10000,'search_period':'2026-09','previous_search_volume':1000}
    result=analyze_evidence('C',[row],['US'])
    assert result['count']==1 and '未判断增长' in result['candidates'][0]['evidence'][0]
    assert analyze_evidence('C',[{**row,'asin':''}],['US'])['count']==0


def test_store_snapshot_difference_is_scoped_to_seller_and_market():
    rows=[{**historical(),'seller_id':'one','snapshot_date':'2026-09-01','snapshot_complete':True},
          {**historical('B0SEASON02'),'seller_id':'one','snapshot_date':'2026-10-01'},
          {**historical('B0SEASON03'),'seller_id':'two','snapshot_date':'2026-10-01'}]
    report=analyze_evidence('I',rows,['US'])
    assert report['count']==1 and report['candidates'][0]['asin']=='B0SEASON02'
    assert '此前完整快照未出现' in report['candidates'][0]['evidence'][0]


def test_rank_gain_is_not_monthly_sales_growth():
    row={**historical(),'current_rank':100,'previous_rank':1000,'window_hours':24,'rank_category':'Home','observed_at':'2026-10-08'}
    report=analyze_evidence('K',[row,{**row,'asin':'B0SEASON02','current_rank':2000}],['US'])
    assert report['count']==1 and '非销量增长率' in report['candidates'][0]['evidence'][0]


@pytest.mark.parametrize('strategy,fields',[
    ('C',{'keyword':'winter decor','search_volume':10000,'search_period':'2026-09'}),
    ('K',{'current_rank':100,'previous_rank':1000,'window_hours':24,'rank_category':'Home','observed_at':'2026-10-08'}),
])
def test_import_strategies_export_workbook(tmp_path,strategy,fields):
    result=run.run_discovery_flow({'request':'分析产品','run_dir':str(tmp_path),'strategy_selection':{'strategy_ids':[strategy],'source_marketplaces':['US']},'discovery_records':[{**historical(),**fields}]})
    assert result['status']=='COMPLETE'
    assert result['workbook']['row_count']==1


def test_month_response_must_match_market_month_and_host():
    def response(url): return SimpleNamespace(url=url,request=SimpleNamespace(url=url,post_data=None))
    base='https://www.sellersprite.com/v3/api/product-research?market=US&month=2025-10'
    assert _matches_month_query(response(base),'US','2025-10')
    assert not _matches_month_query(response(base),'DE','2025-10')
    assert not _matches_month_query(response(base),'US','2025-11')
    assert not _matches_month_query(response(base.replace('www.sellersprite.com','sellersprite.com.evil.test')),'US','2025-10')


@pytest.mark.parametrize('prompt,strategy', [
    ('FBM开发策略','J'), ('新品榜开发策略','E'), ('优质店铺跟踪开发策略','I'),
    ('亚马逊热词','C'), ('历史开发策略','H'), ('排名飙升榜开发策略','K'),
    ('寻找圣诞新品','E'), ('近60天FBM圣诞商品','J'),
])
def test_six_strategy_names_route_without_confusing_seasonal_topics(prompt,strategy):
    assert run.create_task(prompt)['strategy_resolution']['strategy_ids']==[strategy]
