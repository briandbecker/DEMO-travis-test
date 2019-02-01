provider "aws" {
  region     = "us-east-1"
  assume_role {
    role_arn     = "arn:aws:iam::399378614282:role/terraform"
    session_name = "terraform"
  }
}

resource "aws_s3_bucket" "b" {
  bucket = "csa-sentinel-demo"
  acl    = "public-read"
}

