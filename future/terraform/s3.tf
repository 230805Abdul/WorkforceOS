resource "aws_s3_bucket" "resumes" {
  bucket = "${var.project_name}-resumes-${var.environment}"
  tags   = { Name = "${var.project_name}-resumes" }
}

resource "aws_s3_bucket_public_access_block" "resumes" {
  bucket                  = aws_s3_bucket.resumes.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "resumes" {
  bucket = aws_s3_bucket.resumes.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "resumes" {
  bucket = aws_s3_bucket.resumes.id
  versioning_configuration {
    status = "Enabled" # protects against accidental overwrite/delete of uploaded resumes
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "resumes" {
  bucket = aws_s3_bucket.resumes.id
  rule {
    id     = "transition-old-versions"
    status = "Enabled"
    noncurrent_version_transition {
      noncurrent_days = 90
      storage_class   = "GLACIER"
    }
  }
}
