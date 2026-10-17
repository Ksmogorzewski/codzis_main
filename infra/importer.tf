# Importer: task ECS uruchamiany przez EventBridge co 2 h. Pobiera zbiory z API UM Warszawy,
# standaryzuje (src/importer/schema.py) i wrzuca nowe/zmienione rekordy na kolejkę taggera.

# Stan importu (hash per rekord) + surowe odpowiedzi API
resource "aws_s3_bucket" "data" {
  bucket        = "${local.name}-data-${local.suffix}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    id     = "expire-raw-snapshots"
    status = "Enabled"

    filter {
      prefix = "raw/"
    }

    expiration {
      days = var.raw_snapshot_retention_days
    }
  }
}

# Token API dane.um.warszawa.pl - wartość ustawiana poza Terraformem (nie trafia do state'u)
resource "aws_ssm_parameter" "um_api_token" {
  name  = "/${local.name}/um-api-token"
  type  = "SecureString"
  value = "CHANGE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ecr_repository" "importer" {
  name                 = "${local.name}-importer"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "importer" {
  repository = aws_ecr_repository.importer.name
  policy     = aws_ecr_lifecycle_policy.worker.policy
}

resource "aws_cloudwatch_log_group" "importer" {
  name              = "/ecs/${local.name}-importer"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "importer_task" {
  name               = "${local.name}-importer-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy" "importer_task" {
  name = "${local.name}-importer-task"
  role = aws_iam_role.importer_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.events.arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = ["${aws_s3_bucket.data.arn}/state/*", "${aws_s3_bucket.data.arn}/raw/*"]
      },
      {
        # Bez ListBucket brak pliku stanu (pierwszy przebieg) daje AccessDenied zamiast NoSuchKey
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = aws_s3_bucket.data.arn
        Condition = { StringLike = { "s3:prefix" = ["state/*"] } }
      },
    ]
  })
}

resource "aws_ecs_task_definition" "importer" {
  family                   = "${local.name}-importer"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.worker_execution.arn
  task_role_arn            = aws_iam_role.importer_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "importer"
    image     = "${aws_ecr_repository.importer.repository_url}:${var.importer_image_tag}"
    essential = true

    environment = [
      { name = "SQS_QUEUE_URL", value = aws_sqs_queue.events.url },
      { name = "DATA_BUCKET", value = aws_s3_bucket.data.id },
      { name = "AWS_REGION", value = var.region },
      { name = "AWS_DEFAULT_REGION", value = var.region }, # tego używa botocore
    ]

    secrets = [
      { name = "UM_API_TOKEN", valueFrom = aws_ssm_parameter.um_api_token.arn },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.importer.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "importer"
      }
    }
  }])
}

# --- harmonogram: EventBridge uruchamia task bezpośrednio (bez Lambdy) ---

resource "aws_iam_role" "importer_schedule" {
  name = "${local.name}-importer-schedule"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "importer_schedule" {
  name = "${local.name}-importer-schedule"
  role = aws_iam_role.importer_schedule.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Action    = ["ecs:RunTask"]
        Resource  = "arn:aws:ecs:${var.region}:${local.suffix}:task-definition/${aws_ecs_task_definition.importer.family}:*"
        Condition = { ArnEquals = { "ecs:cluster" = aws_ecs_cluster.main.arn } }
      },
      {
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = [aws_iam_role.worker_execution.arn, aws_iam_role.importer_task.arn]
      },
    ]
  })
}

resource "aws_cloudwatch_event_rule" "importer" {
  name                = "${local.name}-importer"
  schedule_expression = var.importer_schedule
}

resource "aws_cloudwatch_event_target" "importer" {
  rule     = aws_cloudwatch_event_rule.importer.name
  arn      = aws_ecs_cluster.main.arn
  role_arn = aws_iam_role.importer_schedule.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.importer.arn_without_revision # zawsze najnowsza rewizja
    task_count          = 1
    # Zwykły Fargate (nie Spot): task trwa ~1 min, a nieudany start przesunąłby import o 2 h
    launch_type = "FARGATE"

    network_configuration {
      subnets          = aws_subnet.public[*].id
      security_groups  = [aws_security_group.worker.id]
      assign_public_ip = true # bez NAT Gateway
    }
  }
}
