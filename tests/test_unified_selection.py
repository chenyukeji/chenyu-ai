import json
from pathlib import Path
import sqlite3
import sys

import pytest

SCRIPTS=Path(__file__).resolve().parents[1]/'plugins/chenyu-kaifa/skills/chenyu-xuanpin/scripts'
sys.path.insert(0,str(SCRIPTS))
import selection_flow as flow
from selection_analysis import analyze_keywords, merge_products, summarize_products
from selection_collectors import amazon_identity, collect_database


def scope(sources=None):
    return {'marketplaces':['US'],'sources':sources or ['sellersprite_new','keyword_trends'],
            'categories':[{'name':'圣诞树装饰','keywords':{'US':['christmas tree ornaments']}}]}


def keyword(month,volume,**extra):
    return {'marketplace':'US','keyword':'tree ornaments','month':month,'search_volume':volume,
            'source_ref':'https://www.sellersprite.com/fixture',**extra}


def product(**extra):
    return {'marketplace':'US','asin':'B012345678','product_name':'Tree ornaments',
            'source_available_date':'2026-09-01','estimated_sales':500,'review_count':8,'price':15,
            'source_ref':'https://www.sellersprite.com/fixture',**extra}


def test_input_market_identity_and_unsupported_domains():
    assert amazon_identity('https://www.amazon.de/dp/B012345678')['marketplace']=='DE'
    assert amazon_identity('https://www.amazon.com/sp?seller=A123456789')['kind']=='store'
    assert amazon_identity('https://www.amazon.com/stores/ABC/page/123')['seller_id'] is None
    for bad in ('https://amazon.com.evil.test/dp/B012345678','https://www.amazon.fr/dp/B012345678','https://user@amazon.com/dp/B012345678'):
        with pytest.raises(ValueError):amazon_identity(bad)


def test_product_link_does_not_default_to_two_markets():
    plan=flow.plan_selection({'request':'分析 https://www.amazon.de/dp/B012345678'})
    assert plan['marketplaces']==['DE'] and plan['blocking_items']
    assert plan['queries'][0]['source']=='amazon_input'


def test_multi_source_plan_keeps_history_windows_and_explicit_scope():
    value=scope(list(flow.SOURCES));value['following_months']=3
    plan=flow.plan_selection({'request':'圣诞树装饰','scope':value,'as_of_date':'2026-10-11'})
    historical=[q for q in plan['queries'] if q['source']=='sellersprite_history']
    assert [q['history_month'] for q in historical]==['2025-10','2025-11','2025-12','2026-01']
    assert all(q['keyword']=='christmas tree ornaments' for q in historical)
    assert any(q.get('unavailable') for q in plan['queries'] if q['source']=='amazon_new_releases')
    assert len({q['id'] for q in plan['queries']})==len(plan['queries'])


def test_keyword_only_evidence_survives_without_asin_and_excludes_partial_month():
    report=analyze_keywords([keyword('2025-09',100),keyword('2026-08',200),keyword('2026-09',300),
                             keyword('2026-10',10000)],'2026-10-11')
    d=report['directions'][0]
    assert d['latest_month']=='2026-09' and d['mom_percent']==50 and d['yoy_percent']==200
    assert d['absolute_change']==100 and len(d['history'])==3


def test_keyword_missing_month_and_zero_base_never_invent_growth():
    d=analyze_keywords([keyword('2026-07',100),keyword('2026-09',200)],'2026-10-11')['directions'][0]
    assert d['mom_percent'] is None and d['yoy_percent'] is None
    d=analyze_keywords([keyword('2026-08',0),keyword('2026-09',200)],'2026-10-11')['directions'][0]
    assert d['mom_percent'] is None and d['absolute_change']==200


def test_conflicting_keyword_observations_require_review():
    d=analyze_keywords([keyword('2026-08',100),keyword('2026-09',200),keyword('2026-09',300)],'2026-10-11')['directions'][0]
    assert d['confidence']=='待核实' and d['mom_percent'] is None


def test_history_and_database_do_not_overwrite_current_sales():
    values=[{'query':{'source':'sellersprite_history','history_month':'2025-12'},'records':[product(estimated_sales=9999)]},
            {'query':{'source':'sellersprite_new'},'records':[product()]},
            {'query':{'source':'new_releases_db'},'records':[product(estimated_sales=0)]}]
    products=merge_products(values)
    assert len(products)==1 and products[0]['current']['estimated_sales']==500
    assert products[0]['historical'][0]['estimated_sales']==9999
    assert len(products[0]['source_types'])==3


def test_missing_data_cannot_receive_positive_priority():
    products=merge_products([{'query':{'source':'sellersprite_new'},'records':[product(price=None)]}])
    rows=summarize_products(products,[{'marketplace':'US','asin':'B012345678','relevant':True,'reason':'相关','priority':'优先研究'}])
    assert rows[0]['优先级']=='待补数据'


def test_resume_reuses_success_and_retries_blocked_source(monkeypatch,tmp_path):
    calls=[]
    def collect(q,p,known):
        calls.append(q['source'])
        if q['source']=='keyword_trends':return {'collection_status':'blocked','records':[],'block_reason':'permission'}
        return {'collection_status':'complete','records':[product()]}
    monkeypatch.setattr(flow,'collect_query',collect)
    payload={'request':'圣诞树装饰','scope':scope(),'run_dir':str(tmp_path),'enrich':False,'as_of_date':'2026-10-11'}
    result=flow.run_selection(payload)
    assert result['status']=='AWAITING_ANALYSIS' and len(result['analysis_requests'])==1
    assert not (tmp_path/'开品结果.xlsx').exists()
    result=flow.run_selection({'run_dir':str(tmp_path),'enrich':False})
    assert calls==['sellersprite_new','keyword_trends','keyword_trends']
    assert result['coverage'][1]['status']=='blocked'


def test_query_budget_resumes_without_recollecting_success(monkeypatch,tmp_path):
    calls=[]
    def collect(q,p,known):
        calls.append(q['source']);return {'collection_status':'complete','records':[product()] if q['source']=='sellersprite_new' else [keyword('2026-09',300)]}
    monkeypatch.setattr(flow,'collect_query',collect)
    p={'scope':scope(),'request':'圣诞树装饰','run_dir':str(tmp_path),'enrich':False,'max_queries':1,'as_of_date':'2026-10-11'}
    assert flow.run_selection(p)['status']=='RUNNING'
    result=flow.run_selection({'run_dir':str(tmp_path),'enrich':False,'max_queries':1})
    assert result['status']=='AWAITING_ANALYSIS' and calls==['sellersprite_new','keyword_trends']


def test_keyword_only_workbook_has_real_history_sheet(monkeypatch,tmp_path):
    monkeypatch.setattr(flow,'collect_query',lambda *args:{'collection_status':'complete','records':[keyword('2026-08',100),keyword('2026-09',300)]})
    result=flow.run_selection({'scope':scope(['keyword_trends']),'run_dir':str(tmp_path),'as_of_date':'2026-10-11'})
    from openpyxl import load_workbook
    wb=load_workbook(result['workbook']['path'])
    assert result['status']=='COMPLETE' and wb['关键词月度明细'].max_row==3
    assert wb['关键词趋势'].cell(2,5).value==200


def test_database_scope_and_readonly_window(tmp_path):
    path=tmp_path/'db.sqlite';con=sqlite3.connect(path)
    con.execute('CREATE TABLE observations(marketplace,category,snapshot_date,rank,asin,title,source_url)')
    con.executemany('INSERT INTO observations VALUES (?,?,?,?,?,?,?)',[
        ('US','party','2026-10-10',1,'B012345678','Party','https://www.amazon.com/gp/new-releases/toys'),
        ('US','other','2026-10-10',1,'B012345679','Other','https://www.amazon.com/gp/new-releases/home')])
    con.commit();con.close();before=path.read_bytes()
    result=collect_database({'db_path':str(path),'marketplace':'US','db_category':'party','as_of_date':'2026-10-11'})
    assert len(result['records'])==1 and path.read_bytes()==before
    with pytest.raises(ValueError):collect_database({'db_path':str(path),'marketplace':'US','as_of_date':'2026-10-11'})


def test_changed_scope_does_not_reuse_reviews(monkeypatch,tmp_path):
    monkeypatch.setattr(flow,'collect_query',lambda *args:{'collection_status':'complete','records':[product()]})
    p={'scope':scope(['sellersprite_new']),'run_dir':str(tmp_path),'as_of_date':'2026-10-11','enrich':False,
       'reviews':[{'marketplace':'US','asin':'B012345678','relevant':True,'priority':'继续观察','reason':'本次商品用途与圣诞装饰相关'}]}
    assert flow.run_selection(p)['status']=='COMPLETE'
    p.pop('reviews');p['scope']['categories'][0]['keywords']['US']=['birthday decorations']
    assert flow.run_selection(p)['status']=='AWAITING_ANALYSIS'


def test_filters_are_enforced_and_formula_text_is_not_executable(monkeypatch,tmp_path):
    monkeypatch.setattr(flow,'collect_query',lambda *args:{'collection_status':'complete','records':[product(product_name='=1+1',price=15)]})
    value=scope(['sellersprite_new']);value['filters']={'price_max':10}
    result=flow.run_selection({'scope':value,'run_dir':str(tmp_path),'enrich':False,
       'reviews':[{'marketplace':'US','asin':'B012345678','relevant':True,'priority':'优先研究','reason':'商品相关'}]})
    assert result['workbook']['row_count']==0
    value['filters']={'price_max':20}
    result=flow.run_selection({'scope':value,'run_dir':str(tmp_path),'enrich':False,
       'reviews':[{'marketplace':'US','asin':'B012345678','relevant':True,'priority':'优先研究','reason':'商品相关'}]})
    from openpyxl import load_workbook
    ws=load_workbook(result['workbook']['path'])['选品结果']
    assert ws.cell(2,3).value=='=1+1' and ws.cell(2,3).data_type=='s'


def test_fresh_response_matching_rejects_other_market_keyword_and_host():
    from types import SimpleNamespace
    from selection_collectors import response_matches
    def response(market='US',keyword='party',host='www.sellersprite.com'):
        url=f'https://{host}/v3/api/product-research'
        return SimpleNamespace(url=url,request=SimpleNamespace(url=url,post_data=json.dumps({'market':market,'keywords':keyword})))
    args={'path':'/v3/api/product-research','expected':{'market':'US','keywords':'party'}}
    assert response_matches(response(),**args)
    assert not response_matches(response(market='DE'),**args)
    assert not response_matches(response(keyword='tree'),**args)
    assert not response_matches(response(host='www.sellersprite.com.evil.test'),**args)


def test_keyword_series_uses_explicit_month_axis():
    from selection_collectors import parse_keyword_series, browser
    rows=parse_keyword_series([{'key':'time','data':['2025年12月','2026年01月']},
                               {'key':'search','data':[100,200]}, {'key':'purchase','data':[2,3]}],
                              'US','tree ornaments','https://www.sellersprite.com/trend')
    assert [r['month'] for r in rows]==['2025-12','2026-01']
    assert rows[1]['purchase_volume']==3
    with pytest.raises(browser.BrowserCollectionError):
        parse_keyword_series([{'key':'time','data':['unknown']},{'key':'search','data':[10]}],
                             'US','tree ornaments','https://www.sellersprite.com/trend')


def test_shortlist_prefers_lexical_fit_but_balances_sources():
    from selection_analysis import balanced_shortlist
    data=[{'query':{'source':'sellersprite_new'},'records':[
        product(asin='B012345678',product_name='Tea tree wipes',filter_keyword='christmas tree ornaments'),
        product(asin='B012345679',product_name='Christmas tree ornaments',filter_keyword='christmas tree ornaments')]},
        {'query':{'source':'amazon_new_releases'},'records':[product(asin='B012345680')]}]
    rows=balanced_shortlist(merge_products(data),2)
    assert [r['asin'] for r in rows]==['B012345679','B012345680']


def test_invalid_scope_values_are_rejected():
    for extra in ({'input_urls':'https://www.amazon.com/dp/B012345678'},
                  {'categories':['tree']},{'filters':{'price_min':float('nan')}}):
        with pytest.raises(ValueError):flow.plan_selection({'scope':{**scope(),**extra}})


def test_placeholder_dates_and_numeric_fields_remain_missing():
    rows=merge_products([{'query':{'source':'sellersprite_new'},'records':[
        product(source_available_date='--',estimated_sales='--',price='15.5')]}])
    assert rows[0]['current'].get('source_available_date') is None
    assert rows[0]['current'].get('estimated_sales') is None
    assert rows[0]['current']['price']==15.5


def test_duplicate_observation_cannot_erase_an_existing_conflict():
    d=analyze_keywords([keyword('2026-09',200),keyword('2026-09',300),keyword('2026-09',200)],'2026-10-11')['directions'][0]
    assert d['confidence']=='待核实'


def test_authentication_failure_stops_repeated_source_logins(monkeypatch,tmp_path):
    calls=[]
    def collect(q,*args):
        calls.append(q['source'])
        return {'collection_status':'blocked','records':[],'block_reason':'sellersprite_login_required'}
    monkeypatch.setattr(flow,'collect_query',collect)
    r=flow.run_selection({'scope':scope(),'run_dir':str(tmp_path)})
    assert calls==['sellersprite_new'] and r['status']=='BLOCKED'
    assert len(r['coverage'])==2 and all(x['reason']=='sellersprite_login_required' for x in r['coverage'])
