# Dispatcher: co kilka minut sprawdza kolejkę i odpala task workera, jeśli jest dość wiadomości
# i żaden worker już nie działa. Worker sam się kończy, gdy kolejka jest pusta.
data "archive_file" "dispatcher" {
  type        = "zip"
  source_dir  = "${path.module}/../src/dispatcher"
  output_path = "${path.module}/build/dispatcher.zip"
  excludes    = ["__pycache__"]
}

resource "aws_cloudwatch_log_group" "dispatcher" {
  name              = "/aws/lambda/${local.name}-dispatcher"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "dispatcher" {
  name = "${local.name}-dispatcher"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "dispatcher" {
  name = "${local.name}-dispatcher"
  role = aws_iam_role.dispatcher.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.dispatcher.arn}:*"
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:GetQueueAttributes"]
        Resource = aws_sqs_queue.events.arn
      },
      {
        Effect    = "Allow"
        Action    = ["ecs:ListTasks"]
        Resource  = "*"
        Condition = { ArnEquals = { "ecs:cluster" = aws_ecs_cluster.main.arn } }
      },
      {
        Effect    = "Allow"
        Action    = ["ecs:RunTask"]
        Resource  = "arn:aws:ecs:${var.region}:${local.suffix}:task-definition/${aws_ecs_task_definition.worker.family}:*"
        Condition = { ArnEquals = { "ecs:cluster" = aws_ecs_cluster.main.arn } }
      },
      {
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = [aws_iam_role.worker_execution.arn, aws_iam_role.worker_task.arn]
      },
    ]
  })
}

resource "aws_lambda_function" "dispatcher" {
  function_name    = "${local.name}-dispatcher"
  role             = aws_iam_role.dispatcher.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "handler.handler"
  filename         = data.archive_file.dispatcher.output_path
  source_code_hash = data.archive_file.dispatcher.output_base64sha256
  memory_size      = 128
  timeout          = 30

  environment {
    variables = {
      EVENTS_QUEUE_URL = aws_sqs_queue.events.url
      CLUSTER          = aws_ecs_cluster.main.arn
      TASK_DEFINITION  = aws_ecs_task_definition.worker.family # zawsze najnowsza rewizja
      SUBNETS          = join(",", aws_subnet.public[*].id)
      SECURITY_GROUP   = aws_security_group.worker.id
    }
  }

  depends_on = [aws_cloudwatch_log_group.dispatcher, aws_iam_role_policy.dispatcher]
}

locals {
  # reguła -> (harmonogram, minimalna liczba wiadomości)
  dispatcher_schedules = {
    threshold = { rate = var.worker_check_minutes, min_messages = var.worker_min_messages }
    max-wait  = { rate = var.worker_max_wait_minutes, min_messages = 1 }
  }
}

resource "aws_cloudwatch_event_rule" "dispatcher" {
  for_each = local.dispatcher_schedules

  name                = "${local.name}-dispatcher-${each.key}"
  schedule_expression = "rate(${each.value.rate} ${each.value.rate == 1 ? "minute" : "minutes"})"
}

resource "aws_cloudwatch_event_target" "dispatcher" {
  for_each = local.dispatcher_schedules

  rule  = aws_cloudwatch_event_rule.dispatcher[each.key].name
  arn   = aws_lambda_function.dispatcher.arn
  input = jsonencode({ minMessages = each.value.min_messages })
}

resource "aws_lambda_permission" "dispatcher" {
  for_each = local.dispatcher_schedules

  statement_id  = "AllowEventBridge-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dispatcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.dispatcher[each.key].arn
}
