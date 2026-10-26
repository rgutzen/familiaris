// The chart's data as it stood on 2026-10-20, TRIMMED for the test: every model
// at 1455 Elo or above (the region where a nomination is possible against the
// catalogue's tier members), plus every row `models.yaml`'s `arena:` names and
// one cheap weak model. Rows are verbatim from
// https://github.com/paraplouis/llm-pareto-frontier `data/synthesized_data.js`,
// fetched 2026-10-22; `dataLastUpdated` is the chart's own. It replaces the
// 2026-10-15 fixture because the chart renamed every slug row to a display name
// in between (14b), and a fixture under the old names pins a mapping that no
// longer exists.
//
// WHY TRIMMED AND NOT THE WHOLE FILE: 295 rows are 49 KB of another project's
// data. The rule a test pins is a comparison, and every comparison that can
// fire is decided by a model at or above the incumbents' Elo. That holds only
// while no judged member sits below 1460 (5 Elo of margin), and a test pins it.
// The live scout reads the whole chart; this is the fixture the rule is held to.
export const data = [
  {"model": "Gemini 4 Argon (High)", "elo": 1524, "input_price": 2.0, "output_price": 10.0, "cheapest_provider": "Google", "votes": 4900, "organization": "Google"},
  {"model": "Muse Wonder (Max)", "elo": 1510, "input_price": 4.0, "output_price": 20.0, "cheapest_provider": "Meta", "votes": 5099, "organization": "Meta"},
  {"model": "Claude Opus 5.5 (High)", "elo": 1509, "input_price": 4.0, "output_price": 20.0, "cheapest_provider": "Anthropic", "votes": 9496, "organization": "Anthropic"},
  {"model": "Claude Fable 5 (High)", "elo": 1504, "input_price": 10.0, "output_price": 50.0, "cheapest_provider": "Anthropic", "votes": 43399, "organization": "Anthropic"},
  {"model": "Claude Opus 4.6 (High)", "elo": 1503, "input_price": 5.0, "output_price": 25.0, "cheapest_provider": "Anthropic", "votes": 82619, "organization": "Anthropic"},
  {"model": "Claude Fable 5.1 (Max)", "elo": 1503, "input_price": 10.0, "output_price": 50.0, "cheapest_provider": "Anthropic", "votes": 15623, "organization": "Anthropic"},
  {"model": "Claude Opus 4.7 (High)", "elo": 1501, "input_price": 5.0, "output_price": 25.0, "cheapest_provider": "Anthropic", "votes": 65131, "organization": "Anthropic"},
  {"model": "Claude Opus 4.6", "elo": 1497, "input_price": 5.0, "output_price": 25.0, "cheapest_provider": "Anthropic", "votes": 87372, "organization": "Anthropic"},
  {"model": "Gemini 3.8 Flash (High)", "elo": 1496, "input_price": 0.825, "output_price": 4.125, "cheapest_provider": "Google", "votes": 41423, "organization": "Google"},
  {"model": "Muse Spark 1.3 (Max)", "elo": 1495, "input_price": 1.25, "output_price": 4.25, "cheapest_provider": "Meta", "votes": 19323, "organization": "Meta"},
  {"model": "Claude Opus 4.7", "elo": 1494, "input_price": 5.0, "output_price": 25.0, "cheapest_provider": "Anthropic", "votes": 66185, "organization": "Anthropic"},
  {"model": "Muse Spark 1.2 (xHigh)", "elo": 1492, "input_price": 1.25, "output_price": 4.25, "cheapest_provider": "Meta", "votes": 9578, "organization": "Meta"},
  {"model": "Claude Opus 5 (Max)", "elo": 1491, "input_price": 5.0, "output_price": 25.0, "cheapest_provider": "Anthropic", "votes": 33683, "organization": "Anthropic"},
  {"model": "Muse Spark 1.1", "elo": 1490, "input_price": 1.25, "output_price": 4.25, "cheapest_provider": "Meta", "votes": 44815, "organization": "Meta"},
  {"model": "Claude Opus 5 (High)", "elo": 1490, "input_price": 5.0, "output_price": 25.0, "cheapest_provider": "Anthropic", "votes": 69307, "organization": "Anthropic"},
  {"model": "Muse Spark", "elo": 1489, "input_price": 1.25, "output_price": 4.25, "cheapest_provider": "Meta", "votes": 14153, "organization": "Meta"},
  {"model": "Gemini 3.7 Flash (High)", "elo": 1489, "input_price": 0.75, "output_price": 3.75, "cheapest_provider": "Google", "votes": 29177, "organization": "Google"},
  {"model": "Kimi K3 (Max)", "elo": 1488, "input_price": 0.239, "output_price": 11.936, "cheapest_provider": "Moonshotai", "votes": 34325, "organization": "Moonshot"},
  {"model": "Gemini 3.1 Pro Preview", "elo": 1487, "input_price": 2.0, "output_price": 12.0, "cheapest_provider": "Google", "votes": 129523, "organization": "Google"},
  {"model": "Gemini 3 Pro", "elo": 1485, "input_price": 2.0, "output_price": 12.0, "cheapest_provider": "Google", "votes": 42059, "organization": "Google"},
  {"model": "GPT-5.6 Sol (xHigh)", "elo": 1484, "input_price": 4.0, "output_price": 20.0, "cheapest_provider": "OpenAI", "votes": 41803, "organization": "OpenAI"},
  {"model": "Gemini 3.6 Flash (High)", "elo": 1483, "input_price": 0.75, "output_price": 3.75, "cheapest_provider": "Google", "votes": 36079, "organization": "Google"},
  {"model": "Qwen3.8-Max", "elo": 1483, "input_price": 2.0, "output_price": 6.0, "cheapest_provider": "Alibaba", "votes": 29418, "organization": "Alibaba"},
  {"model": "GPT-5.5 (High)", "elo": 1481, "input_price": 5.0, "output_price": 30.0, "cheapest_provider": "OpenAI", "votes": 69340, "organization": "OpenAI"},
  {"model": "Claude Opus 4.8 (High)", "elo": 1481, "input_price": 5.0, "output_price": 25.0, "cheapest_provider": "Anthropic", "votes": 64063, "organization": "Anthropic"},
  {"model": "GLM-5.3 (Max)", "elo": 1481, "input_price": 0.079, "output_price": 1.4, "cheapest_provider": "Z Ai", "votes": 24035, "organization": "Z.ai"},
  {"model": "MiMo-V2.6-Pro", "elo": 1480, "input_price": 0.435, "output_price": 0.87, "cheapest_provider": "Xiaomi", "votes": 4065, "organization": "Xiaomi"},
  {"model": "GPT-6.1 Sol (Max)", "elo": 1479, "input_price": 2.0, "output_price": 10.0, "cheapest_provider": "OpenAI", "votes": 7453, "organization": "OpenAI"},
  {"model": "Gemini 3.5 Flash (High)", "elo": 1477, "input_price": 1.5, "output_price": 9.0, "cheapest_provider": "Google", "votes": 48479, "organization": "Google"},
  {"model": "Claude Sonnet 5.5 (xHigh)", "elo": 1477, "input_price": 2.0, "output_price": 10.0, "cheapest_provider": "Anthropic", "votes": 8126, "organization": "Anthropic"},
  {"model": "GPT-5.5", "elo": 1477, "input_price": 5.0, "output_price": 30.0, "cheapest_provider": "OpenAI", "votes": 70970, "organization": "OpenAI"},
  {"model": "GLM-5.2 (Max)", "elo": 1476, "input_price": 0.0341, "output_price": 7.0, "cheapest_provider": "Z Ai", "votes": 51221, "organization": "Z.ai"},
  {"model": "Gemini 3.5 Flash (Medium)", "elo": 1476, "input_price": 1.5, "output_price": 9.0, "cheapest_provider": "Google", "votes": 47228, "organization": "Google"},
  {"model": "GPT-6 Astra (Max)", "elo": 1476, "input_price": 10.0, "output_price": 50.0, "cheapest_provider": "OpenAI", "votes": 13293, "organization": "OpenAI"},
  {"model": "GPT-5.2 Chat (20260210)", "elo": 1475, "input_price": 1.75, "output_price": 14.0, "cheapest_provider": "OpenAI", "votes": 35991, "organization": "OpenAI"},
  {"model": "DeepSeek-V4.1-Flash-20260910 (Max)", "elo": 1475, "input_price": 0.15, "output_price": 0.6, "cheapest_provider": "DeepSeek", "votes": 13444, "organization": "DeepSeek"},
  {"model": "GPT-5.4 (High)", "elo": 1475, "input_price": 2.5, "output_price": 15.0, "cheapest_provider": "OpenAI", "votes": 64755, "organization": "OpenAI"},
  {"model": "GLM-5.3-Flash", "elo": 1475, "input_price": 0.0052, "output_price": 0.1985, "cheapest_provider": "Z Ai", "votes": 36095, "organization": "Z.ai"},
  {"model": "Grok 4.20 Beta 1", "elo": 1475, "input_price": 1.25, "output_price": 2.5, "cheapest_provider": "xAI", "votes": 27918, "organization": "xAI"},
  {"model": "Claude Opus 4.8", "elo": 1474, "input_price": 5.0, "output_price": 25.0, "cheapest_provider": "Anthropic", "votes": 65151, "organization": "Anthropic"},
  {"model": "Qwen3.7-Max-Preview", "elo": 1474, "input_price": 1.475, "output_price": 4.425, "cheapest_provider": "Alibaba", "votes": 3942, "organization": "Alibaba"},
  {"model": "Claude Opus 4.5 (High, 32K, 20251101)", "elo": 1474, "input_price": 5.0, "output_price": 25.0, "cheapest_provider": "Anthropic", "votes": 37500, "organization": "Anthropic"},
  {"model": "GPT-5.5 Instant", "elo": 1473, "input_price": 5.0, "output_price": 30.0, "cheapest_provider": "OpenAI", "votes": 27154, "organization": "OpenAI"},
  {"model": "Gemini 3 Flash", "elo": 1473, "input_price": 0.5, "output_price": 3.0, "cheapest_provider": "Google", "votes": 31311, "organization": "Google"},
  {"model": "Claude Sonnet 4.6", "elo": 1472, "input_price": 3.0, "output_price": 15.0, "cheapest_provider": "Anthropic", "votes": 70931, "organization": "Anthropic"},
  {"model": "Grok 4.20 Beta (Reasoning, 0309)", "elo": 1472, "input_price": 1.25, "output_price": 2.5, "cheapest_provider": "xAI", "votes": 66403, "organization": "xAI"},
  {"model": "Grok 4.20 Multi-Agent Beta (0309)", "elo": 1471, "input_price": 1.25, "output_price": 2.5, "cheapest_provider": "xAI", "votes": 64920, "organization": "xAI"},
  {"model": "Claude Opus 4.5 (20251101)", "elo": 1470, "input_price": 5.0, "output_price": 25.0, "cheapest_provider": "Anthropic", "votes": 72863, "organization": "Anthropic"},
  {"model": "GPT-5.6 Terra (xHigh)", "elo": 1467, "input_price": 2.0, "output_price": 12.0, "cheapest_provider": "OpenAI", "votes": 45201, "organization": "OpenAI"},
  {"model": "MiMo-V2.5-Pro", "elo": 1466, "input_price": 0.3045, "output_price": 0.609, "cheapest_provider": "Xiaomi", "votes": 77367, "organization": "Xiaomi"},
  {"model": "Grok 4.5", "elo": 1465, "input_price": 2.0, "output_price": 6.0, "cheapest_provider": "xAI", "votes": 39844, "organization": "xAI"},
  {"model": "GLM-5.1", "elo": 1465, "input_price": 1.4, "output_price": 4.4, "cheapest_provider": "Z Ai", "votes": 64352, "organization": "Z.ai"},
  {"model": "Grok 4.1 (Thinking)", "elo": 1465, "input_price": 2.0, "output_price": 6.0, "cheapest_provider": "xAI", "votes": 66478, "organization": "xAI"},
  {"model": "GPT-5.4", "elo": 1465, "input_price": 2.5, "output_price": 15.0, "cheapest_provider": "OpenAI", "votes": 67829, "organization": "OpenAI"},
  {"model": "Qwen3.5-Max-Preview", "elo": 1465, "input_price": 0.3, "output_price": 1.8, "cheapest_provider": "Alibaba", "votes": 22608, "organization": "Alibaba"},
  {"model": "DeepSeek-V4-Pro (High, 20260813)", "elo": 1465, "input_price": 0.15, "output_price": 0.6, "cheapest_provider": "DeepSeek", "votes": 9805, "organization": "DeepSeek"},
  {"model": "Claude Sonnet 5 (High)", "elo": 1461, "input_price": 2.0, "output_price": 10.0, "cheapest_provider": "Anthropic", "votes": 50871, "organization": "Anthropic"},
  {"model": "Kimi K2.6", "elo": 1461, "input_price": 0.65, "output_price": 3.41, "cheapest_provider": "Moonshotai", "votes": 40014, "organization": "Moonshot"},
  {"model": "Qwen3.6-Max-Preview", "elo": 1460, "input_price": 0.1875, "output_price": 1.125, "cheapest_provider": "Alibaba", "votes": 5427, "organization": "Alibaba"},
  {"model": "Grok 4.1", "elo": 1459, "input_price": 2.0, "output_price": 6.0, "cheapest_provider": "xAI", "votes": 68635, "organization": "xAI"},
  {"model": "GPT-6 Sol (Max)", "elo": 1459, "input_price": 2.0, "output_price": 10.0, "cheapest_provider": "OpenAI", "votes": 13790, "organization": "OpenAI"},
  {"model": "Gemini 3 Flash (Minimal)", "elo": 1458, "input_price": 0.5, "output_price": 3.0, "cheapest_provider": "Google", "votes": 91005, "organization": "Google"},
  {"model": "DeepSeek-V4-Pro", "elo": 1458, "input_price": 0.9553, "output_price": 1.9105, "cheapest_provider": "DeepSeek", "votes": 57564, "organization": "DeepSeek"},
  {"model": "GLM-5", "elo": 1457, "input_price": 1.0, "output_price": 3.2, "cheapest_provider": "Z Ai", "votes": 29268, "organization": "Z.ai"},
  {"model": "Claude Sonnet 4.5 (High, 32K, 20250929)", "elo": 1456, "input_price": 3.0, "output_price": 15.0, "cheapest_provider": "Anthropic", "votes": 83921, "organization": "Anthropic"},
  {"model": "GPT-5.1 (High)", "elo": 1456, "input_price": 1.25, "output_price": 10.0, "cheapest_provider": "OpenAI", "votes": 41651, "organization": "OpenAI"},
  {"model": "Qwen3.7-Plus", "elo": 1456, "input_price": 0.32, "output_price": 1.28, "cheapest_provider": "Alibaba", "votes": 42030, "organization": "Alibaba"},
  {"model": "Grok 4.6 (High)", "elo": 1455, "input_price": 2.0, "output_price": 6.0, "cheapest_provider": "xAI", "votes": 30919, "organization": "xAI"},
  {"model": "Gemini 3.5 Flash-Lite", "elo": 1455, "input_price": 0.3, "output_price": 2.5, "cheapest_provider": "Google", "votes": 35820, "organization": "Google"},
  {"model": "Claude Sonnet 4.5 (20250929)", "elo": 1455, "input_price": 3.0, "output_price": 15.0, "cheapest_provider": "Anthropic", "votes": 82669, "organization": "Anthropic"},
  {"model": "DeepSeek-V4-Pro Preview (High)", "elo": 1455, "input_price": 0.15, "output_price": 0.6, "cheapest_provider": "DeepSeek", "votes": 54879, "organization": "DeepSeek"},
  {"model": "Mistral Large 4", "elo": 1433, "input_price": 1.36, "output_price": 4.18, "cheapest_provider": "Mistral", "votes": 9308, "organization": "Mistral"},
  {"model": "Mistral Medium 3.5", "elo": 1426, "input_price": 1.5, "output_price": 7.5, "cheapest_provider": "Mistral", "votes": 11785, "organization": "Mistral"},
  {"model": "Ling-flash-2.0", "elo": 1343, "input_price": 0.021, "output_price": 0.063, "cheapest_provider": "Inclusionai", "votes": 6950, "organization": "Ant Group"}
];

export const dataLastUpdated = "2026-10-20";
export const minElo = 1000;
export const excludeFree = true;
