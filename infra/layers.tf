# Wspólny kod Lambd API (src/layers/common/python/codzis_common) jako Lambda Layer.
# Zip zawiera python/codzis_common/..., runtime rozpakowuje go do /opt, a /opt/python jest w sys.path,
# więc w kodzie: from codzis_common.http import ApiError, response, ...
data "archive_file" "common_layer" {
  type        = "zip"
  source_dir  = "${path.module}/../src/layers/common"
  output_path = "${path.module}/build/common_layer.zip"
  excludes    = ["python/codzis_common/__pycache__"]
}

resource "aws_lambda_layer_version" "common" {
  layer_name               = "${local.name}-common"
  description              = "codzis_common: wspólne helpery HTTP dla Lambd API"
  filename                 = data.archive_file.common_layer.output_path
  source_code_hash         = data.archive_file.common_layer.output_base64sha256
  compatible_runtimes      = ["python3.13"]
  compatible_architectures = ["arm64"]
}
