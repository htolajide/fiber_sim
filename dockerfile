# Dockerfile - Geant4 v11.3.2 from local tar.gz (no recursive ENV)

FROM ubuntu:20.04

LABEL maintainer="taofeek.hammed.dokt@pw.edu.pl"
LABEL description="Geant4 v11.3.2 for fiber FPI radiation simulation"

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libx11-dev \
    libxmu-dev \
    libglu1-mesa-dev \
    libxt-dev \
    libexpat1-dev \
    libqt5opengl5-dev \
    qtbase5-dev \
    && rm -rf /var/lib/apt/lists/*

# Create user
RUN useradd -m geant4 && echo "geant4:geant4" | chpasswd
USER geant4
WORKDIR /home/geant4

# Copy source
COPY geant4-v11.3.2.tar.gz /home/geant4/

# Extract and flatten into 'geant4-src'
RUN echo "📦 Extracting geant4-v11.3.2.tar.gz..." && \
    mkdir geant4-src && \
    tar -xzf geant4-v11.3.2.tar.gz -C geant4-src --strip-components=1 && \
    if [ ! -f "geant4-src/CMakeLists.txt" ]; then \
        echo "❌ ERROR: CMakeLists.txt not found in geant4-src!" >&2; \
        exit 1; \
    fi && \
    echo "✅ Source extracted."

# Build and install Geant4
RUN mkdir geant4-build geant4-install
WORKDIR /home/geant4/geant4-build
RUN cmake \
    -DCMAKE_INSTALL_PREFIX=/home/geant4/geant4-install \
    -DGEANT4_INSTALL_DATA=ON \
    -DGEANT4_USE_OPENGL_X11=ON \
    -DGEANT4_USE_QT=ON \
    -DGEANT4_BUILD_MULTITHREADED=OFF \
    ../geant4-src && \
    make -j$(nproc) && \
    make install && \
    echo "🎉 Geant4 v11.3.2 built and installed!"

# ✅ Set environment variables (avoid recursive LD_LIBRARY_PATH)
ENV PATH="/home/geant4/geant4-install/bin:${PATH}"
ENV GEANT4_DIR="/home/geant4/geant4-install/lib/cmake/Geant4"
ENV GEANT4_INSTALL="/home/geant4/geant4-install"

# No LD_LIBRARY_PATH override — let dynamic linker use rpath from binaries

# Final work directory
WORKDIR /home/geant4/work
CMD ["/bin/bash"]