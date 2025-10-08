# Dockerfile - Self-built Geant4 v11.1 for Fiber Radiation Simulation

# Base image
FROM ubuntu:20.04

# Labels
LABEL maintainer="you@university.edu"
LABEL description="Geant4 v11.1 with CMake, Qt, and essential libraries for optical fiber radiation modeling"

# Prevent interactive prompts during package install
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
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
    wget \
    git \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user 'geant4'
RUN useradd -m geant4 && echo "geant4:geant4" | chpasswd
USER geant4
WORKDIR /home/geant4

# Download Geant4 v11.1 source (official release from CERN)
RUN echo "Downloading Geant4 v11.1..." && \
    wget https://geant4-data.web.cern.ch/releases/geant4-v11.1.tar.gz --no-check-certificate && \
    tar -xzf geant4-v11.1.tar.gz && \
    mkdir geant4-build geant4-install && \
    echo "Geant4 source extracted."

# Build and install Geant4
WORKDIR /home/geant4/geant4-build
RUN cmake \
    -DCMAKE_INSTALL_PREFIX=/home/geant4/geant4-install \
    -DGEANT4_INSTALL_DATA=ON \
    -DGEANT4_USE_OPENGL_X11=ON \
    -DGEANT4_USE_QT=ON \
    -DGEANT4_BUILD_MULTITHREADED=OFF \
    ../geant4-v11.1 && \
    make -j$(nproc) && \
    make install && \
    echo "Geant4 v11.1 built and installed."

# Set environment variables
ENV PATH="/home/geant4/geant4-install/bin:${PATH}"
ENV LD_LIBRARY_PATH="/home/geant4/geant4-install/lib:${LD_LIBRARY_PATH}"

# Final work directory for user code
WORKDIR /home/geant4/work
CMD ["/bin/bash"]