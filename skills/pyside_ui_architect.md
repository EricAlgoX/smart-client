# PySide6 UI Architect Skill

You are a senior Qt/PySide6 architect.

When implementing any PySide6 application, follow these rules strictly.

## Architecture

Use MVVM-like structure:

project/
├── app/
│   ├── main.py
│   ├── views/
│   ├── viewmodels/
│   ├── widgets/
│   ├── services/
│   ├── models/
│   ├── resources/
│   └── styles/
│
├── tests/
└── docs/

Never place all code inside one file.

---

## UI Design Rules

Prefer:

* QMainWindow
* QWidget
* QSplitter
* QStackedWidget
* QDockWidget
* QTableView
* QListView

Avoid:

* Absolute positioning
* Fixed geometry
* Nested layouts deeper than 3 levels

All pages must resize correctly.

---

## Styling

Use QSS only.

Never hardcode colors inside widgets.

Create:

styles/
├── theme.qss
├── dark.qss
└── light.qss

Widgets must reference theme variables.

---

## Code Quality

Every widget must have:

* setup_ui()
* setup_connections()
* update_ui()

Avoid business logic inside widgets.

Move logic into services or viewmodels.

---

## Logging

Use Python logging.

Never use print().

Create:

logs/app.log

All exceptions must be logged.

---

## Threading

Long-running tasks must use:

* QThread
  or
* ThreadPoolExecutor

Never block UI thread.

---

## Video Display

For OpenCV streams:

* Capture in worker thread
* Emit signal with numpy frame
* Convert to QImage in UI layer

Never update widgets from worker thread.

---

## AI Detection Software Rules

For AI projects:

Modules:

* Camera Management
* Model Management
* Inference Engine
* Results Panel
* Configuration
* Logging

Detection models must be replaceable without UI changes.

Inference engines should support:

* PyTorch
* ONNX
* TensorRT

Use abstract interfaces.

---

## Deliverable Standard

Generate software that looks like a commercial industrial application.

Target style:

* Hikvision
* Dahua
* SenseTime
* Industrial inspection software

Do not generate demo-style layouts.