import json
import os
import time
from typing import Any, Dict, List, Optional

from utils.constants import DATA_DIR


class AgentState:
    def __init__(self) -> None:
        self._path: str = os.path.join(DATA_DIR, "agent_state.json")
        self._state: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "source_health": {},
            "recommendation_history": [],
            "failed_sources": {},
            "upgrade_logs": [],
            "scoring_metrics_performance": {},
            "detected_issues": [],
            "resolved_issues": [],
            "version": 2,
            "last_upgrade": None,
        }

    def _save(self) -> None:
        with open(self._path, "w") as f:
            json.dump(self._state, f, indent=2)

    def log_source_result(self, source: str, success: bool, detail: Optional[str] = None) -> None:
        health = self._state["source_health"]
        if source not in health:
            health[source] = {"success": 0, "failure": 0, "last_status": "unknown"}
        if success:
            health[source]["success"] += 1
            health[source]["last_status"] = "ok"
        else:
            health[source]["failure"] += 1
            health[source]["last_status"] = "failed"
            if source not in self._state["failed_sources"]:
                self._state["failed_sources"][source] = []
            self._state["failed_sources"][source].append({"time": time.time(), "detail": detail})
        self._detect_issues()
        self._save()

    def log_recommendation(self, recommendations: List[Dict[str, Any]]) -> None:
        self._state["recommendation_history"].append({
            "time": time.time(),
            "picks": [
                {
                    "ticker": r["ticker"],
                    "score": r["total_score"],
                    "price": r.get("price"),
                    "sector": r.get("sector"),
                }
                for r in recommendations
            ],
        })
        self._save()

    def log_upgrade(self, message: str) -> None:
        self._state["upgrade_logs"].append({"time": time.time(), "message": message})
        self._state["last_upgrade"] = time.time()
        self._save()

    def get_source_priority(self, default_priority: Dict[str, int]) -> Dict[str, int]:
        priority = dict(default_priority)
        for source, info in self._state["source_health"].items():
            total = info["success"] + info["failure"]
            if total > 5 and info["failure"] / total > 0.5:
                if source in priority:
                    priority[source] += 10
                self.log_upgrade(f"数据源 {source} 可靠性下降 ({info['failure']}/{total} 失败), 降低优先级")
        return priority

    def get_health_status(self) -> Dict[str, Any]:
        return self._state["source_health"]

    def get_upgrade_logs(self) -> List[Dict[str, Any]]:
        return self._state["upgrade_logs"][-20:]

    def get_summary(self) -> Dict[str, Any]:
        health = self._state["source_health"]
        health_summary: Dict[str, Any] = {}
        for source, info in health.items():
            total = info["success"] + info["failure"]
            rate = info["success"] / total * 100 if total > 0 else 0
            health_summary[source] = {
                "成功率": f"{rate:.0f}%",
                "状态": info["last_status"],
                "总请求": total,
            }
        return {
            "数据源健康度": health_summary,
            "推荐次数": len(self._state["recommendation_history"]),
            "升级日志数": len(self._state["upgrade_logs"]),
            "检测到的问题": self._state["detected_issues"][-5:][::-1],
            "最后升级": self._state["last_upgrade"],
        }

    def should_try_fallback(self, source: str) -> bool:
        info = self._state["source_health"].get(source, {})
        failures = info.get("failure", 0)
        success = info.get("success", 0)
        total = failures + success
        if total >= 3 and failures / total > 0.6:
            return True
        return False

    def _detect_issues(self) -> None:
        health = self._state["source_health"]
        issues: List[str] = []

        for source, info in health.items():
            total = info["success"] + info["failure"]
            if total >= 3 and info["failure"] / total > 0.8:
                issues.append(f"数据源 {source} 失败率过高 ({info['failure']}/{total}) — 建议检查网络或更换数据源")

        sec_cik_lookups = [s for s in health if "cik_lookup" in s]
        cik_failures = sum(1 for s in sec_cik_lookups if health[s]["failure"] > health[s]["success"])
        if cik_failures > len(sec_cik_lookups) * 0.5:
            issues.append(f"CIK 映射查询失败率过高 ({cik_failures}/{len(sec_cik_lookups)}) — SEC 可能已更新 API")

        if "sec:cik_map" in health:
            map_info = health["sec:cik_map"]
            if map_info["failure"] > 0 and map_info["success"] == 0:
                issues.append("SEC CIK 映射表下载失败 — SEC 公司代码映射可能已不可用")

        all_sec_sources = [
            s for s in health
            if s.startswith("sec:") and s not in ["sec:cik_map"]
            and "cik_lookup" not in s
        ]
        sec_total = sum(health[s]["success"] + health[s]["failure"] for s in all_sec_sources)
        sec_fail = sum(health[s]["failure"] for s in all_sec_sources)
        if sec_total > 5 and sec_fail / sec_total > 0.5:
            issues.append(f"SEC EDGAR 整体可用性下降 ({sec_fail}/{sec_total} 失败) — SEC 可能限制了访问频率")

        new_issues = [i for i in issues if i not in self._state.get("detected_issues", [])]
        if new_issues:
            self._state.setdefault("detected_issues", []).extend(new_issues)
            for issue in new_issues:
                self.log_upgrade(f"🔍 检测到问题: {issue}")

        resolved = [
            i for i in self._state.get("detected_issues", [])
            if i not in issues
            and i not in self._state.get("resolved_issues", [])
        ]
        if resolved:
            self._state.setdefault("resolved_issues", []).extend(resolved)
            for issue in resolved:
                self.log_upgrade(f"✅ 问题已解决: {issue}")

        self._state["detected_issues"] = issues


agent_state = AgentState()
