-- One row per Gemini call: input, raw answer, tokens, server latency (last 24h)
SELECT
  logging_time,
  JSON_VALUE(full_request,  '$.contents[0].parts[0].text')              AS user_input,
  JSON_VALUE(full_response, '$.candidates[0].content.parts[0].text')    AS raw_answer,
  CAST(JSON_VALUE(full_response, '$.usageMetadata.promptTokenCount')     AS INT64) AS tok_in,
  CAST(JSON_VALUE(full_response, '$.usageMetadata.candidatesTokenCount') AS INT64) AS tok_out,
  ROUND(CAST(JSON_VALUE(metadata, '$.request_latency') AS FLOAT64))     AS server_ms
FROM `nexusforge-ai-dev.j4_ai_logs.request_response_logging`
WHERE logging_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
ORDER BY logging_time DESC
