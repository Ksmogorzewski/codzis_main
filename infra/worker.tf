resource "aws_ecr_repository" "worker" {
  name                 = "${local.name}-worker"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "worker" {
  repository = aws_ecr_repository.worker.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Trzymaj 3 ostatnie obrazy"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 3
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_ecs_cluster" "main" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${local.name}-worker"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Rola, której używa ECS przy starcie taska (pull obrazu, logi)
resource "aws_iam_role" "worker_execution" {
  name               = "${local.name}-worker-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "worker_execution" {
  role       = aws_iam_role.worker_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Klucz DeepSeek: SSM SecureString (standard tier = darmowy). Wartość ustawiasz poza Terraformem,
# żeby nie trafiła do state'u:
#   aws ssm put-parameter --name /codzis/deepseek-api-key --type SecureString --overwrite --value sk-...
resource "aws_ssm_parameter" "deepseek_api_key" {
  name  = "/${local.name}/deepseek-api-key"
  type  = "SecureString"
  value = "CHANGE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_iam_role_policy" "worker_execution_secrets" {
  name = "${local.name}-worker-secrets"
  role = aws_iam_role.worker_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["ssm:GetParameters"]
      # Rola wykonawcza jest wspólna dla taggera i importera
      Resource = [aws_ssm_parameter.deepseek_api_key.arn, aws_ssm_parameter.um_api_token.arn]
    }]
  })
}

# Rola kodu workera
resource "aws_iam_role" "worker_task" {
  name               = "${local.name}-worker-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy" "worker_task" {
  name = "${local.name}-worker-task"
  role = aws_iam_role.worker_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes"]
        Resource = aws_sqs_queue.events.arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem"]
        Resource = aws_dynamodb_table.events.arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.submissions.arn
      },
      {
        # Zdjęcia wydarzeń w standardzie (tagger/images.py): sprawdzenie, czy plik już jest, i zapis
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${aws_s3_bucket.photos.arn}/photos/events/*"
      },
      {
        # Bez ListBucket brak pliku daje 403 zamiast 404 (tagger nie odróżniłby „nie ma” od „brak uprawnień”)
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.photos.arn
      },
    ]
  })
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.worker_execution.arn
  task_role_arn            = aws_iam_role.worker_task.arn

  # FARGATE_SPOT wymaga X86_64 - obraz budować z --platform linux/amd64
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "worker"
    image     = "${aws_ecr_repository.worker.repository_url}:${var.worker_image_tag}"
    essential = true

    environment = [
      { name = "SQS_QUEUE_URL", value = aws_sqs_queue.events.url },
      { name = "DYNAMODB_TABLE", value = aws_dynamodb_table.events.name },
      { name = "SUBMISSIONS_TABLE", value = aws_dynamodb_table.submissions.name },
      # Zdjęcia wydarzeń w standardzie: bucket zdjęć, publicznie przez CloudFront panelu pod /photos/*
      { name = "PHOTOS_BUCKET", value = aws_s3_bucket.photos.id },
      { name = "PHOTOS_BASE_URL", value = local.website_origin },
      { name = "AWS_REGION", value = var.region },
      { name = "AWS_DEFAULT_REGION", value = var.region }, # tego używa botocore
    ]

    secrets = [
      { name = "DEEPSEEK_API_KEY", valueFrom = aws_ssm_parameter.deepseek_api_key.arn },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.worker.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "worker"
      }
    }
  }])
}
