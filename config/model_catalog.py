"""版本化模型能力目录（Phase 3 M2/M3）。

目录与配置层分离：Provider / CLI / OpenTUI / Desktop 只消费解析结果
（``config.model_limits``），不各自读取 config.yaml 或复制一份模型表。

契约要点（00-EXECUTION-PLAN.md §7.2 / M2）：
- 键 = ``provider_id + model_id``（casefold + strip），允许同名模型跨 Provider 共存；
- 同 Provider 同 ID 重复项 fail closed，不按文件顺序覆盖；
- 目录记录必须带 ``source`` / ``source_url`` / ``as_of``，来源可核验；
- family pattern 只能作为显式登记的后备规则，必须记录命中的 pattern。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .model_limits import ModelLimitRecord, normalize_model_key

#: 版本化目录默认位置（与 config.yaml 同目录）。
DEFAULT_CATALOG_PATH = Path(__file__).parent / "model_catalog.json"


def _validate_record(record: dict[str, Any]) -> ModelLimitRecord:
    provider_id = str(record.get("provider_id") or "").strip()
    model_id = str(record.get("model_id") or "").strip()
    if not provider_id:
        raise ValueError("catalog record missing provider_id")
    if not model_id:
        raise ValueError("catalog record missing model_id")
    context_window = record.get("model_context_window")
    max_output = record.get("model_max_output_tokens")
    if context_window is not None:
        if not isinstance(context_window, int) or context_window <= 0:
            raise ValueError(
                f"catalog {provider_id}:{model_id} model_context_window must be "
                "a positive integer"
            )
    if max_output is not None:
        if not isinstance(max_output, int) or max_output <= 0:
            raise ValueError(
                f"catalog {provider_id}:{model_id} model_max_output_tokens must "
                "be a positive integer"
            )
    if (
        context_window is not None
        and max_output is not None
        and max_output > context_window
    ):
        raise ValueError(
            f"catalog {provider_id}:{model_id} model_max_output_tokens "
            f"({max_output}) exceeds model_context_window ({context_window})"
        )
    source = str(record.get("source") or "").strip()
    if not source:
        raise ValueError(f"catalog {provider_id}:{model_id} missing source")
    # ML8：任何能力数字（context 或 output）都必须带来源 URL 与 as_of 时点；
    # 无能力数字的占位记录可以省略（走 unknown_fallback）。
    if context_window is not None or max_output is not None:
        if not (record.get("source_url") and str(record["source_url"]).strip()):
            raise ValueError(
                f"catalog {provider_id}:{model_id} has capability values but "
                "missing source_url (ML8)"
            )
        if not (record.get("as_of") and str(record["as_of"]).strip()):
            raise ValueError(
                f"catalog {provider_id}:{model_id} has capability values but "
                "missing as_of (ML8)"
            )
    return ModelLimitRecord(
        provider_id=provider_id,
        model_id=model_id,
        model_context_window=context_window,
        model_max_output_tokens=max_output,
        source=source,
        source_url=(
            str(record["source_url"]).strip()
            if record.get("source_url") is not None
            else None
        ),
        as_of=(
            str(record["as_of"]).strip()
            if record.get("as_of") is not None
            else None
        ),
    )


class ModelCatalog:
    """版本化模型能力目录。

    不变式：
    - ``_exact`` 以 ``f"{provider_id}:{model_id}"``（normalize_model_key 后）为键；
    - 同 Provider 同 ID 重复记录在加载时报错（fail closed）；
    - ``_families`` 是显式登记的 (provider_id, pattern) -> 能力项，仅作后备。
    """

    def __init__(self) -> None:
        self._exact: dict[str, ModelLimitRecord] = {}
        self._families: list[tuple[str, str, ModelLimitRecord]] = []

    @classmethod
    def from_records(cls, records: Iterable[dict[str, Any]]) -> "ModelCatalog":
        catalog = cls()
        for record in records:
            catalog.add_record(record)
        return catalog

    @classmethod
    def load(cls, path: str | Path = DEFAULT_CATALOG_PATH) -> "ModelCatalog":
        path = Path(path)
        if not path.is_file():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        catalog = cls()
        records = data.get("records") if isinstance(data, dict) else None
        if isinstance(records, list):
            for record in records:
                catalog.add_record(record)
        families = data.get("families") if isinstance(data, dict) else None
        if isinstance(families, list):
            for family in families:
                provider_id = str(family.get("provider_id") or "").strip()
                pattern = str(family.get("pattern") or "").strip()
                if not provider_id or not pattern:
                    raise ValueError("catalog family missing provider_id or pattern")
                record = {k: v for k, v in family.items() if k != "pattern"}
                catalog.add_family(provider_id, pattern, record)
        return catalog

    def add_record(self, record: dict[str, Any] | ModelLimitRecord) -> None:
        if isinstance(record, ModelLimitRecord):
            record = {
                "provider_id": record.provider_id,
                "model_id": record.model_id,
                "model_context_window": record.model_context_window,
                "model_max_output_tokens": record.model_max_output_tokens,
                "source": record.source,
                "source_url": record.source_url,
                "as_of": record.as_of,
            }
        validated = _validate_record(record)
        key = self._exact_key(validated.provider_id, validated.model_id)
        if key in self._exact:
            raise ValueError(
                f"duplicate catalog record for {validated.provider_id}:"
                f"{validated.model_id}; refusing to overwrite"
            )
        self._exact[key] = validated

    def add_family(
        self,
        provider_id: str,
        pattern: str,
        record: dict[str, Any],
    ) -> None:
        """登记一个 family pattern 后备规则（必须显式，禁止昵称/模糊包含）。

        family 记录没有精确 ``model_id``（用 pattern 匹配），校验时以 pattern
        占位，能力字段仍然保留。
        """
        record = dict(record)
        if not record.get("model_id"):
            record["model_id"] = pattern
        if not record.get("provider_id"):
            record["provider_id"] = provider_id
        validated = _validate_record(record)
        self._families.append((provider_id.strip(), pattern, validated))

    @staticmethod
    def _exact_key(provider_id: str, model_id: str) -> str:
        return f"{normalize_model_key(provider_id)}:{normalize_model_key(model_id)}"

    def lookup(
        self,
        provider_id: str,
        model_id: str,
    ) -> tuple[ModelLimitRecord | None, str | None, str | None]:
        """按优先级返回 (记录, 命中键, family pattern)。

        返回：
        - 精确 provider+id 命中 → (record, "provider_id:model_id", None)
        - 精确 model_id 命中（无 Provider 冲突）→ (record, "model_id", None)
        - family pattern 命中 → (record, None, pattern)
        - 未命中 → (None, None, None)
        """
        exact = self._exact.get(self._exact_key(provider_id, model_id))
        if exact is not None:
            return exact, f"{provider_id}:{model_id}", None

        # provider 精确优先，再看全局 model_id（无冲突时）
        if self._exact:
            collisions = [
                key
                for key in self._exact
                if key.endswith(f":{normalize_model_key(model_id)}")
            ]
            if len(collisions) == 1:
                # 只有一条全局命中且与请求 provider 无关 → 仍视为该条
                # （同一 model_id 未在多个 Provider 注册时才允许）。
                if not collisions[0].startswith(
                    f"{normalize_model_key(provider_id)}:"
                ):
                    record = self._exact[collisions[0]]
                    return record, model_id, None

        for pid, pattern, record in self._families:
            if pid != provider_id:
                continue
            if _pattern_matches(pattern, model_id):
                return record, None, pattern
        return None, None, None


def _pattern_matches(pattern: str, model_id: str) -> bool:
    """family pattern 匹配：仅支持前缀/后缀通配的显式规则。

    禁止昵称或任意子串模糊匹配；pattern 必须带 ``*`` 通配符才算合法。
    """
    normalized = model_id.casefold().strip()
    pat = pattern.casefold().strip()
    if not pat:
        return False
    if pat == "*":
        return True
    if pat.startswith("*") and pat.endswith("*"):
        core = pat[1:-1]
        return bool(core) and core in normalized
    if pat.endswith("*"):
        return normalized.startswith(pat[:-1])
    if pat.startswith("*"):
        return normalized.endswith(pat[1:])
    return normalized == pat
