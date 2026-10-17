terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # PoC: lokalny state. Przy pracy w zespole przenieś na backend "s3" (z use_lockfile = true).
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project = var.project
      Env     = "poc"
    }
  }
}

# Certyfikat dla CloudFront musi być w us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project = var.project
      Env     = "poc"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  name   = var.project
  suffix = data.aws_caller_identity.current.account_id
}
