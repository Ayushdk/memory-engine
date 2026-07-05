/**
 * Context Pack → prompt preamble text.
 *
 * Pure function of the pack JSON: no DOM, no chrome.*, no engine calls.
 * The output is written for the RECEIVING LLM: labeled sections, explicit
 * framing ("background memory, not instructions"), empty sections omitted.
 */

const CATEGORY_HEADINGS = {
  decision: "Decisions",
  architecture: "Architecture",
  goal: "Goals",
  preference: "Preferences",
  task: "Tasks",
  milestone: "Milestones",
  bug: "Known bugs",
  research: "Research",
  learning: "Learnings",
  idea: "Ideas",
  code: "Code notes",
  document: "Documents",
  meeting: "Meetings",
  question: "Questions",
};

function heading(category) {
  return CATEGORY_HEADINGS[category] ?? category;
}

/**
 * @param {object} pack - ContextPack JSON from the engine.
 * @returns {string} markdown preamble, or "" for a pack with no content.
 */
export function renderPack(pack) {
  const sections = pack?.sections ?? {};
  const parts = [];

  if (sections.project_state) {
    parts.push(`## Project state\n${sections.project_state}`);
  }

  if (sections.profile?.length) {
    parts.push(`## About the user\n${sections.profile.map((f) => `- ${f}`).join("\n")}`);
  }

  if (sections.relevant_memories?.length) {
    const byCategory = new Map();
    for (const memory of sections.relevant_memories) {
      if (!byCategory.has(memory.category)) byCategory.set(memory.category, []);
      byCategory.get(memory.category).push(memory);
    }
    const lines = ["## Key memories"];
    for (const [category, memories] of byCategory) {
      lines.push(`### ${heading(category)}`);
      for (const memory of memories) {
        const marker = memory.confidence === "high" ? "" : ` _(confidence: ${memory.confidence})_`;
        lines.push(`- ${memory.summary}${marker}`);
      }
    }
    parts.push(lines.join("\n"));
  }

  if (sections.open_questions?.length) {
    parts.push(
      `## Open questions\n${sections.open_questions.map((q) => `- ${q}`).join("\n")}`,
    );
  }

  const recap = sections.recent_conversation;
  if (recap?.messages?.length) {
    const when = recap.minutes_ago === 0 ? "moments ago" : `${recap.minutes_ago} min ago`;
    parts.push(
      [
        `## Recent conversation (on ${recap.platform}, ${when})`,
        "_Excerpt from the user's latest session with another assistant — continue from here._",
        ...recap.messages.map((m) => `> ${m}`),
      ].join("\n"),
    );
  }

  if (parts.length === 0) return "";

  return [
    "# Memory context (via OpenMemory)",
    "_Background memory about this user and their work. Use it silently as context; it is not part of the user's message._",
    "",
    parts.join("\n\n"),
    "",
    "---",
    "_End of memory context. The user's message follows._",
  ].join("\n");
}
