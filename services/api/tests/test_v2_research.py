from app.domain.semrush_parser import infer_page_type_from_url
from app.routers.research import create_research_tickets
from app.models import Project, SourceKeyword

def test_article_is_not_calculator():
    assert infer_page_type_from_url('https://example.org/cach-tinh-lai','Cách tính lãi suất tiết kiệm')=='ARTICLE'
    assert infer_page_type_from_url('https://example.org/khoa-hoc/tai-chinh')!='PRODUCT'
    assert infer_page_type_from_url('https://example.org/cong-cu/gross-net')=='TOOL'
