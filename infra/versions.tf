terraform {
  required_version = ">= 1.10" # use_lockfile w backendzie s3

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

  # Bucket tworzy scripts/bootstrap-tfstate.sh. Lock: plik <key>.tflock w tym samym buckecie (bez DynamoDB).
  backend "s3" {
    bucket       = "codzis-tfstate-370478231901"
    key          = "codzis/terraform.tfstate"
    region       = "eu-central-1"
    encrypt      = true
    use_lockfile = true
  }
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
