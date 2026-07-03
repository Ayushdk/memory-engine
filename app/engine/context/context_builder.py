"""Context Builder (architecture.md §4, §7): ranked memories → Context Pack.

Pure transformation. Fixed template: Project State → Profile facts → Relevant
memories (grouped by category) → Open questions. Token budget from Settings;
over budget, the lowest-ranked relevant memories are dropped first — Project
State and Profile are mandatory and never trimmed.
"""

from typing import Sequence

from app.core.config import get_settings
from app.engine.retrieval.ranking_engine import RankingResult
from app.models.domain.context_pack import ContextMemory, ContextPack, ContextSections
from app.models.domain.memory import Memory
from app.models.enums import MemoryCategory, MemoryView
from app.services.tokenizer_service import estimate_tokens


def _text(memory: Memory) -> str:
    return memory.summary or memory.content


class ContextBuilder:
    def build(
        self,
        ranking: RankingResult,
        session_id: str,
        project_state: str | None = None,
        profile_memories: Sequence[Memory] = (),
    ) -> ContextPack:
        profile = [_text(m) for m in profile_memories]
        seen = {m.id for m in profile_memories}

        relevant: list[Memory] = []
        open_questions: list[str] = []
        for memory in ranking.ranked_memories:  # ranking order preserved throughout
            if memory.id in seen:
                continue
            if memory.category is MemoryCategory.QUESTION:
                open_questions.append(_text(memory))
            elif memory.view is MemoryView.PROFILE:
                profile.append(_text(memory))
            else:
                relevant.append(memory)

        # Budget: mandatory sections are counted but never trimmed.
        budget = get_settings().context_token_budget
        fixed = (
            estimate_tokens(project_state or "")
            + sum(estimate_tokens(t) for t in profile)
            + sum(estimate_tokens(t) for t in open_questions)
        )
        while relevant and fixed + sum(estimate_tokens(_text(m)) for m in relevant) > budget:
            relevant.pop()  # lowest-ranked first

        # Group by category, groups ordered by their best-ranked member.
        buckets: dict[MemoryCategory, list[Memory]] = {}
        for memory in relevant:
            buckets.setdefault(memory.category, []).append(memory)
        relevant_memories = [
            ContextMemory(category=m.category, summary=_text(m), confidence=m.confidence)
            for group in buckets.values()
            for m in group
        ]

        return ContextPack(
            session_id=session_id,
            token_estimate=fixed + sum(estimate_tokens(_text(m)) for m in relevant),
            sections=ContextSections(
                project_state=project_state,
                profile=profile,
                relevant_memories=relevant_memories,
                open_questions=open_questions,
            ),
        )
