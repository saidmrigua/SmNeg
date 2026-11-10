from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from smneg import window
from smneg.export import ExportMetadata
from smneg.models import FrameItem


@pytest.mark.parametrize('missing', [{0}, {1}, {0, 1}])
def test_missing_full_source_never_exports_preview(tmp_path, monkeypatch, missing):
    items = [FrameItem(i, str(tmp_path / f'{i}.nef'), np.ones((2, 2, 3))) for i in range(2)]
    options = MagicMock()
    options.exec.return_value = True
    options.info.return_value = {}
    options.selected_indices.return_value = [0, 1]
    options.metadata.return_value = ExportMetadata(*([''] * 11))
    options.file_format.currentData.return_value = 'jpeg'
    options.output_names.return_value = ['0.jpg', '1.jpg']
    options.destination.text.return_value = str(tmp_path)
    options.quality.value.return_value = 95
    options.max_edge.value.return_value = 0
    options.sequence_parameters.return_value = (1, 3)
    options.embed.isChecked.return_value = False
    options.sidecar.isChecked.return_value = False
    monkeypatch.setattr(window, 'ExportDialog', lambda *args: options)
    progress = MagicMock()
    progress.wasCanceled.return_value = False
    monkeypatch.setattr(window, 'QProgressDialog', lambda *args: progress)
    box = MagicMock()
    box.clickedButton.return_value = None
    messages = MagicMock(return_value=box)
    monkeypatch.setattr(window, 'QMessageBox', messages)
    saves = []
    monkeypatch.setattr(window, 'save_image', lambda path, *args, **kwargs: saves.append(path.name) or (2, 2))
    app = SimpleNamespace(items=items, current_idx=0, session_info={}, persist_project=lambda: True,
        load_scan=lambda path, **kwargs: None if int(Path(path).stem) in missing else np.ones((2, 2, 3)),
        render_frame=MagicMock(return_value=np.zeros((2, 2, 3), dtype=np.uint8)))
    window.SMnegWindow.export_batch(app)
    assert saves == [f'{i}.jpg' for i in range(2) if i not in missing]
    assert app.render_frame.call_count == 2 - len(missing)
    assert 'Full-resolution source unavailable' in box.setText.call_args.args[0]
