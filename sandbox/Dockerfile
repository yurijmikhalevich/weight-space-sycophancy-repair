# The editing agent's kernel, with the libraries the Sparks Exp 8 kernel had. PyTorch is the CPU build (the
# aarch64 wheel on PyPI is CPU-only); the kernel turns gradients off. The model itself never runs here.
FROM python:3.13-slim@sha256:8d9d0b8bcf6506481eae4907c18f5e3e7902e629f5f6d684f9e7c32e85e3ddf0
RUN pip install --no-cache-dir numpy==2.5.4 scipy==1.18.1 scikit-learn==1.9.1 torch==2.14.1 pandas==3.1.0 \
    sympy==1.14.0 networkx==3.7 safetensors==0.8.0 tokenizers==0.23.3
RUN useradd --create-home agent
USER agent
