# Headless ftl_bench — runs the REAL FTL + the bench Hyperspace mod under Xvfb, no display, no GPU.
#
# The FTL game is NOT baked into this image (licensing). Bind-mount a Linux FTL install at /ftl
# (a dir containing FTL.amd64 + ftl.dat + data/ + the stock `FTL` launcher) for the verify/run
# modes. The `probe` mode needs no game — it validates the headless display stack alone.
#
# Build context = this directory (docker/headless). `run.sh` stages vendor/ before building.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Headless display + FTL/HS runtime libs:
#   Xvfb + Mesa software GL (llvmpipe, no GPU) + SDL2 + X client libs + FTL audio codecs.
# The harness core is pure stdlib (pyproject dependencies = []), so python3 alone suffices.
RUN apt-get update && apt-get install -y --no-install-recommends \
      xvfb x11-utils x11-xserver-utils \
      libgl1 libglx-mesa0 libgl1-mesa-dri libglu1-mesa mesa-utils \
      libsdl2-2.0-0 \
      libx11-6 libxext6 libxrandr2 libxcursor1 libxi6 libxss1 libxinerama1 libxfixes3 libxrender1 \
      libopenal1 libvorbisfile3 libvorbis0a libogg0 libasound2t64 \
      python3 python3-pip \
      ca-certificates curl unzip rsync procps xz-utils \
  && rm -rf /var/lib/apt/lists/*

# Vendored build inputs (staged host-side by run.sh, so the image build is offline/hermetic):
# the Linux Hyperspace .so, liblua, the two .ftl mods, the hot-reload dev lua, the FTLMan binary,
# and the harness wheel. FTLMan is fetched on the host because the build container here can't
# reach api.github.com (apt over http works, github API HTTPS times out).
COPY vendor/ /opt/hs/

# FTLMan patches ftl.dat with Hyperspace.ftl + ftl_bench_bridge.ftl (cross-platform tool).
RUN install -m 0755 /opt/hs/ftlman /usr/local/bin/ftlman

# Install the harness (no deps) — gives the `ftlbench` CLI with adapter/scenarios/prompts/mod bundled.
RUN python3 -m pip install --no-cache-dir --break-system-packages /opt/hs/ftl_bench-*.whl

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY probe_gl.py   /opt/hs/probe_gl.py
RUN chmod +x /usr/local/bin/entrypoint.sh

# Headless defaults: FTL's old OpenGL runs on Mesa's llvmpipe software rasterizer under Xvfb;
# SDL audio goes to the dummy driver so no sound server is needed.
ENV DISPLAY=:99 \
    SDL_VIDEODRIVER=x11 \
    SDL_AUDIODRIVER=dummy \
    LIBGL_ALWAYS_SOFTWARE=1 \
    GALLIUM_DRIVER=llvmpipe \
    XVFB_WHD=1280x720x24
# FTL_SAVE_DIR is set by the entrypoint to FTL's actual Linux user folder
# (~/.local/share/FasterThanLight) so the game and the harness rendezvous on the bridge files.

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["probe"]
