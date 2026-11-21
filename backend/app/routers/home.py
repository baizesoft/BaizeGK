"""首页相关接口。"""
from __future__ import annotations

from fastapi import APIRouter

from app.config import config
from app.schemas import FeatureItem, HomeResponse

router = APIRouter(tags=["home"])


@router.get("/api/home", response_model=HomeResponse)
def get_home() -> HomeResponse:
    """返回首页展示所需的全部数据，前端纯展示、不写死文案。"""
    app_cfg = config.get("app", {})
    return HomeResponse(
        app_name=app_cfg.get("name", "白泽公考"),
        version=app_cfg.get("version", "0.1.0"),
        title="白泽公考",
        subtitle="铜仁与重庆个人备考",
        slogan="看公告、练对应试卷、回查作答。",
        features=[
            FeatureItem(icon="Brain", title="限时练习", desc="按地区选卷，保留判分和本地复盘材料。"),
            FeatureItem(icon="Target", title="职位表初筛", desc="明确条件先筛，不确定条件回表核实。"),
        ],
        cta_text="开始备考",
        cta_url="/",
    )
