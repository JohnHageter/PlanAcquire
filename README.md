# PlanAcquire

Scripted camera acquisition software for behavioral experiments. Controls cameras (IDS, OpenCV) and records video via `.acq` protocol scripts.

## Features

- Live camera preview with watch-window cropping
- Script engine for automating recording sessions
- Timelapse recording

## Requirements

- uEye runtime for IDS UI cameras
- IDS peak SDK for IDS cameras

## Installation

Download and unzip `PlanAcquire.zip` from the [Releases](../../releases) page and run `PlanAcquire.exe`.

## Protocol scripts

`.acq` scripts are loaded via the script editor in the UI. See [`planacquire/examples/protocols/`](planacquire/examples/protocols/) for examples and a full command reference. The command reference is also available from the software in the `help` menu.

