# ElectrumX for Verus + status page for umbrelOS.
#
# Everything fetched here is pinned: git sources by commit, the NEON header by sha256,
# Python packages by version. The build ends with a self-test against real mainnet blocks.

FROM python:3.8-slim-bookworm AS build

RUN apt-get update \
	&& apt-get install -y --no-install-recommends build-essential ca-certificates curl git libleveldb-dev libsodium-dev \
	&& rm -rf /var/lib/apt/lists/*

RUN python -m venv /venv
ENV PATH=/venv/bin:$PATH
RUN pip install --no-cache-dir pip==24.3.1 setuptools==75.3.0 wheel==0.45.1 pybind11==2.13.6

# Native VerusHash module. The "verushash" name on PyPI is an unrelated package, so build from source.
ARG VERUSHASHPY_COMMIT=7bfc08b97b616eedd3b056ac7ca0c51d410344b1
# SSE2NEON.h as shipped by the Verus daemon when verushashpy's ARM code was written
ARG SSE2NEON_COMMIT=cf4fd450912777ac803dedb905861f08acbe4cc6
ARG SSE2NEON_SHA256=6c8e662998c74315b585e22d549c8aacdedd194abf886f5eafc5bc14acd19328
COPY verushash /build/verushash
RUN set -eux; \
	git clone https://github.com/VerusCoin/verushashpy /build/verushashpy; \
	cd /build/verushashpy; \
	git checkout --detach "${VERUSHASHPY_COMMIT}"; \
	curl -fsSL -o src/crypto/SSE2NEON.h "https://raw.githubusercontent.com/VerusCoin/VerusCoin/${SSE2NEON_COMMIT}/src/crypto/SSE2NEON.h"; \
	echo "${SSE2NEON_SHA256}  src/crypto/SSE2NEON.h" | sha256sum -c -; \
	python /build/verushash/arm_compat.py .; \
	cp /build/verushash/setup.py setup.py; \
	pip install --no-cache-dir --no-deps --no-build-isolation .

COPY requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir -r /build/requirements.txt

# VerusCoin's ElectrumX fork, plus the fix that makes it hash current (VerusHash 2.2 / PBaaS) headers correctly
ARG ELECTRUMX_COMMIT=2281692cb25554429ac8014e7801ef207810b03a
COPY patches /build/patches
RUN set -eux; \
	git clone https://github.com/VerusCoin/electrumx /opt/electrumx; \
	cd /opt/electrumx; \
	git checkout --detach "${ELECTRUMX_COMMIT}"; \
	git apply /build/patches/verus-hash-v2b2.patch; \
	rm -rf .git tests docs contrib

COPY tests /build/tests
RUN python /build/tests/selftest.py /opt/electrumx

FROM python:3.8-slim-bookworm

RUN apt-get update \
	&& apt-get install -y --no-install-recommends libleveldb1d libsodium23 \
	&& rm -rf /var/lib/apt/lists/*

COPY --from=build /venv /venv
COPY --from=build /opt/electrumx /opt/electrumx
COPY app /app

ENV PATH=/venv/bin:$PATH \
	PYTHONUNBUFFERED=1 \
	DB_DIRECTORY=/data/db

USER 1000:1000
EXPOSE 3000 17485
VOLUME /data

CMD ["python", "/app/supervisor.py"]
