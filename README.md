# pdf_toolbox
pdf 解析基础函数


## pdf是否是文字类型/扫描类型的区分

```shell
cat s3_pdf_path.example.pdf | parallel --colsep ' ' -j 10 "python pdf_meta_scan.py --s3-pdf-path {2} --s3-profile {1}"


```