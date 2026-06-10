"""gui_file_dialog.py 测试：mock tkinter，无需真实显示环境"""
import pytest

pytest.importorskip("tkinter")

import epycon.gui_file_dialog as gfd


class _FakeRoot:
    def withdraw(self):
        pass

    def lift(self):
        pass

    def attributes(self, *args):
        pass

    def focus_force(self):
        pass

    def update(self):
        pass

    def destroy(self):
        pass


def test_open_dialog_file_selected(monkeypatch, capsys):
    monkeypatch.setattr(gfd.tk, "Tk", lambda: _FakeRoot())
    monkeypatch.setattr(
        gfd.filedialog, "askopenfilename", lambda **kw: "C:/data/ecg.h5"
    )
    assert gfd.open_dialog() is True
    # 路径必须输出到 stdout 供父进程读取
    assert "C:/data/ecg.h5" in capsys.readouterr().out


def test_open_dialog_cancelled(monkeypatch, capsys):
    monkeypatch.setattr(gfd.tk, "Tk", lambda: _FakeRoot())
    monkeypatch.setattr(gfd.filedialog, "askopenfilename", lambda **kw: "")
    assert gfd.open_dialog() is False
    assert capsys.readouterr().out == ""


def test_open_dialog_tk_error_returns_false(monkeypatch, capsys):
    def boom():
        raise RuntimeError("no display")

    monkeypatch.setattr(gfd.tk, "Tk", boom)
    assert gfd.open_dialog() is False
    assert "Error" in capsys.readouterr().err
