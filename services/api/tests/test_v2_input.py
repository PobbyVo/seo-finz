from pathlib import Path
import unicodedata
import pytest
from app.domain.taxonomy_parser import parse_topic_source_file

@pytest.mark.parametrize('name', ['bo_key_p01.tsv', 'bo_key_p01_original.tsv'])
def test_p01_regions_and_metadata(name):
    raw=(Path(__file__).parent/'fixtures'/name).read_bytes()
    p=parse_topic_source_file(raw,name)
    assert len(p.topic_pillars)==1
    assert len(p.content_items)==2
    assert sum(len(i['keyword_rows']) for i in p.content_items)==12
    assert [i['primary_keyword'] for i in p.content_items]==['lương gross net là gì','cách deal lương']
    assert not [w for w in p.warnings if w['severity']=='ERROR']
    assert p.content_items[0]['keyword_rows'][0]['funnel_stage']=='TOFU'
    assert p.topic_pillars[0]['notes']

@pytest.mark.parametrize('old,new,code', [('TOFU','INVALID','F0-GIAI-DOAN'),('Chính','Phụ','F0-KEY-CHINH'),('P01.1','P99.1','F0-PILLAR')])
def test_f0_errors(old,new,code):
    raw=(Path(__file__).parent/'fixtures/bo_key_p01_original.tsv').read_text().replace(old,new)
    p=parse_topic_source_file(unicodedata.normalize('NFD',raw).encode(),'p01.tsv')
    assert any(w['code']==code and w['severity']=='ERROR' and w['row'] and w['column'] for w in p.warnings)
