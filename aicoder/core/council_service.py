"""
Council Service - Multi-perspective AI analysis
Synchronous version
"""

import json
import os
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from aicoder.utils.log import LogUtils
from aicoder.core.config import Config


@dataclass
class CouncilMember:
    """Council member definition"""

    name: str
    role: str
    instructions: str
    enabled: bool = True


class CouncilService:
    """Council service for multi-perspective analysis"""

    def __init__(self):
        self.council_dir = os.path.expanduser("~/.config/aicoder-mini/council")
        self.moderator_instructions = None
        self.session_active = False

    def start_session(self, messages: List[Dict[str, Any]]) -> None:
        """Start a council session"""
        self.session_active = True
        self.session_messages = messages

    def end_session(self) -> None:
        """End the council session"""
        self.session_active = False

    def load_members(
        self, filters: Optional[List[str]] = None
    ) -> Tuple[List[CouncilMember], str]:
        """Load council members from filesystem"""
        members = []

        # Default council members if directory doesn't exist
        if not os.path.exists(self.council_dir):
            return self._get_default_members(filters)

        # Load members from files
        try:
            for filename in os.listdir(self.council_dir):
                if not filename.endswith(".json"):
                    continue

                filepath = os.path.join(self.council_dir, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                member = CouncilMember(
                    name=data.get("name", filename[:-5]),
                    role=data.get("role", "advisor"),
                    instructions=data.get("instructions", ""),
                    enabled=data.get("enabled", True),
                )

                # Apply filters
                if not member.enabled:
                    continue
                if filters and member.name not in filters:
                    continue

                members.append(member)
        except Exception as e:
            LogUtils.warn(f"Failed to load council members: {e}")
            return self._get_default_members(filters)

        # Load moderator instructions
        moderator_file = os.path.join(self.council_dir, "moderator.json")
        if os.path.exists(moderator_file):
            try:
                with open(moderator_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.moderator_instructions = data.get("instructions", "")
            except:
                self.moderator_instructions = self._get_default_moderator_instructions()
        else:
            self.moderator_instructions = self._get_default_moderator_instructions()

        return members, self.moderator_instructions

    def get_member_opinion(
        self, member: CouncilMember, messages: List[Dict[str, Any]]
    ) -> str:
        """Get opinion from a council member"""
        # Create prompt for this member
        prompt = self._create_member_prompt(member, messages)

        # This would make an API call in real implementation
        # For now, return a mock response
        return f"[{member.name}] This needs careful consideration from a {member.role} perspective."

    def get_consensus(
        self, opinions: List[str], moderator: str, messages: List[Dict[str, Any]]
    ) -> str:
        """Get consensus from all opinions"""
        # Create moderator prompt
        prompt = self._create_consensus_prompt(opinions, moderator, messages)

        # This would make an API call in real implementation
        # For now, return a mock consensus
        return "After considering all perspectives, the consensus is to proceed with caution and thorough testing."

    def _get_default_members(
        self, filters: Optional[List[str]]
    ) -> Tuple[List[CouncilMember], str]:
        """Get default council members"""
        members = [
            CouncilMember(
                name="optimist",
                role="optimistic advisor",
                instructions="Always look for the positive opportunities and benefits. Focus on what could go right.",
            ),
            CouncilMember(
                name="pessimist",
                role="cautious advisor",
                instructions="Always identify potential risks and problems. Focus on what could go wrong.",
            ),
            CouncilMember(
                name="engineer",
                role="technical advisor",
                instructions="Focus on technical feasibility, implementation details, and architectural considerations.",
            ),
        ]

        # Apply filters
        if filters:
            members = [m for m in members if m.name in filters]

        return members, self._get_default_moderator_instructions()

    def _get_default_moderator_instructions(self) -> str:
        """Get default moderator instructions"""
        return """You are the moderator for a council discussion. Review all opinions and provide:
1. A balanced synthesis of all perspectives
2. Key points of agreement and disagreement
3. A recommended course of action
Be objective and constructive."""

    def _create_member_prompt(
        self, member: CouncilMember, messages: List[Dict[str, Any]]
    ) -> str:
        """Create prompt for council member"""
        prompt = f"""You are {member.name}, a {member.role}.

Your instructions: {member.instructions}

Here is the conversation to analyze:

"""

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            prompt += f"{role}: {content}\n\n"

        prompt += f"\nProvide your analysis from your perspective as {member.name}."
        return prompt

    def _create_consensus_prompt(
        self, opinions: List[str], moderator: str, messages: List[Dict[str, Any]]
    ) -> str:
        """Create prompt for reaching consensus"""
        prompt = f"""{moderator}

Here are the opinions from council members:

"""

        for i, opinion in enumerate(opinions, 1):
            prompt += f"Member {i}: {opinion}\n\n"

        prompt += """
Original conversation:

"""

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            prompt += f"{role}: {content}\n\n"

        prompt += "\nPlease provide a consensus analysis and recommendation."
        return prompt
