# Kolejka eventów do otagowania. Wiadomość = JSON array rekordów w kształcie API UM Warszawy
# (rekordy partnera mają dodatkowo "id" i "source": "partner").
resource "aws_sqs_queue" "events" {
  name = "${local.name}-events"
  # Tagger odbiera do 10 wiadomości naraz, a każda to wywołania LLM (timeout 120 s, 3 próby)
  visibility_timeout_seconds = 1800
  # Wiadomości mogą czekać na próg workera, więc maksymalna retencja
  message_retention_seconds = 1209600 # 14 dni

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.events_dlq.arn
    maxReceiveCount     = 5
  })
}

# Wiadomości, których worker nie przetworzył 5 razy
resource "aws_sqs_queue" "events_dlq" {
  name                      = "${local.name}-events-dlq"
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue_redrive_allow_policy" "events_dlq" {
  queue_url = aws_sqs_queue.events_dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.events.arn]
  })
}
