import os, re, configparser

import boto3
from loguru import logger
from boto3.s3.transfer import TransferConfig
from botocore.config import Config


def parse_aws_param(profile):
    # 解析配置文件
    config_file = os.path.join(os.path.expanduser("~"), ".aws", "config")
    credentials_file = os.path.join(os.path.expanduser("~"), ".aws", "credentials")
    config = configparser.ConfigParser()
    config.read(credentials_file)
    config.read(config_file)
    # 获取 AWS 账户相关信息
    ak = config.get(profile, "aws_access_key_id")
    sk = config.get(profile, "aws_secret_access_key")
    if profile == "default":
        s3_str = config.get(f"{profile}", "s3")
    else:
        s3_str = config.get(f"profile {profile}", "s3")
    end_match = re.search("endpoint_url[\s]*=[\s]*([^\s\n]+)[\s\n]*$", s3_str, re.MULTILINE)
    if end_match:
        endpoint = end_match.group(1)
    else:
        raise ValueError(f"aws 配置文件中没有找到 endpoint_url")
    style_match = re.search("addressing_style[\s]*=[\s]*([^\s\n]+)[\s\n]*$", s3_str, re.MULTILINE)
    if style_match:
        addressing_style = style_match.group(1)
    else:
        addressing_style = "path"
    return ak, sk, endpoint, addressing_style


def parse_bucket_key(s3_full_path: str):
    """
    输入 s3://bucket/path/to/my/file.txt
    输出 bucket, path/to/my/file.txt
    """
    s3_full_path = s3_full_path.strip()
    if s3_full_path.startswith("s3://"):
        s3_full_path = s3_full_path[5:]
    if s3_full_path.startswith("/"):
        s3_full_path = s3_full_path[1:]
    bucket, key = s3_full_path.split("/", 1)
    return bucket, key


def read_pdf(pdf_path: str, s3_profile: str):
    if pdf_path.startswith("s3://"):
        ak, sk, end_point, addressing_style = parse_aws_param(s3_profile)
        cli = boto3.client(service_name="s3", aws_access_key_id=ak, aws_secret_access_key=sk, endpoint_url=end_point,
                           config=Config(s3={'addressing_style': addressing_style}))
        bucket_name, bucket_key = parse_bucket_key(pdf_path)
        res = cli.get_object(Bucket=bucket_name, Key=bucket_key)
        file_content = res["Body"].read()
        return file_content
    else:
        with open(pdf_path, "rb") as f:
            return f.read()
        
def list_dir(dir_path:str, s3_profile:str):
    """
    列出dir_path下的所有文件
    """
    ret = []
    
    if dir_path.startswith("s3"):
        ak, sk, end_point, addressing_style = parse_aws_param(s3_profile)
        s3info = re.findall(r"s3:\/\/([^\/]+)\/(.*)", dir_path)
        bucket, path = s3info[0][0], s3info[0][1]
        try:
            cli = boto3.client(service_name="s3", aws_access_key_id=ak, aws_secret_access_key=sk, endpoint_url=end_point,
                                            config=Config(s3={'addressing_style': addressing_style}))
            def list_obj_scluster():
                marker = None
                while True:
                    list_kwargs = dict(MaxKeys=1000, Bucket=bucket, Prefix=path)
                    if marker:
                        list_kwargs['Marker'] = marker
                    response = cli.list_objects(**list_kwargs)
                    contents = response.get("Contents", [])
                    yield from contents
                    if not response.get("IsTruncated") or len(contents)==0:
                        break
                    marker = contents[-1]['Key']


            for info in list_obj_scluster():
                file_path = info['Key']
                #size = info['Size']

                if path!="":
                    afile = file_path[len(path):]
                    if afile.endswith(".json"):
                        ret.append(f"s3://{bucket}/{file_path}")
                        
            return ret

        except Exception as e:
            logger.exception(e)
            exit(-1)
    else: #本地的目录，那么扫描本地目录并返会这个目录里的所有jsonl文件
        
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                if file.endswith(".json"):
                    ret.append(os.path.join(root, file))
        ret.sort()
        return ret

# def get_s3_object(path):
#     src_cli_config = Config(**{
#
#         "connect_timeout": 60,
#         "read_timeout": 20,
#         "max_pool_connections": 500,
#         "s3": {
#             "addressing_style": "path",
#         },
#         "retries": {
#             "max_attempts": 3,
#         }
#     })
#     full_path = f"{bucket_name}/{bucket_prefix}/{path}"
#     try:
#         src_cli = boto3.session.Session().client("s3", aws_access_key_id=ak, aws_secret_access_key=sk, endpoint_url=endpoint, region_name='', config=src_cli_config)
#         res = src_cli.get_object(Bucket=bucket_name, Key=f"{bucket_prefix}/{path}")
#         file_content = res["Body"].read()
#         return file_content
#     except Exception as e:
#         logger.error(f"get_s3_object({full_path}) error: {e}")
#         return b''

if __name__=="__main__":
    s3_path = "s3://llm-pdf-text/layout_det/scihub/scimag07865000-07865999/10.1007/s10729-011-9175-6.pdf/"
    s3_profile = "langchao"
    ret = list_dir(s3_path, s3_profile)
    print(ret)
    