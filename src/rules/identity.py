"""组合标识：同一组单品无论从哪条枚举路径得到，hash 都相同。

放在规则层，是因为求解器排序（轮换修正按 hash 命中）与仓储层记录反馈
都要用它；反过来规则层不能 import 仓储层。
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable


def outfit_hash(garment_ids: Iterable[int]) -> str:
    """id 升序去重后逗号拼接，取 sha1 前 16 位。

    同一组单品无论从哪件锚定、以什么顺序枚举，hash 都一样。
    """
    payload = ",".join(str(i) for i in sorted(set(garment_ids)))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


__all__ = ["outfit_hash"]
