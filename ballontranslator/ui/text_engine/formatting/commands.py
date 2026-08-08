from typing import List, Callable, Dict
import copy

try:
    from qtpy.QtWidgets import QUndoCommand
except:
    from qtpy.QtGui import QUndoCommand

from ... import shared_widget as SW
from ballontranslator.utils.fontformat import FontFormat, px2pt
from ballontranslator.utils.io_utils import empty_func
from ..item import TextBlkItem
from ..editing.commands import RotateItemCommand

global_default_set_kwargs = dict(set_selected=False, restore_cursor=False)
local_default_set_kwargs = dict(set_selected=True, restore_cursor=True)



class TextStyleUndoCommand(QUndoCommand):

    def __init__(self, style_func: Callable, params: Dict, redo_values: List, undo_values: List):
        super().__init__()
        self.style_func = style_func
        self.params = params
        self.redo_values = redo_values
        self.undo_values = undo_values

    def redo(self) -> None:
        self.style_func(values=self.redo_values, **self.params)

    def undo(self) -> None:
        self.style_func(values=self.undo_values, **self.params)


def wrap_fntformat_input(values: str, blkitems: List[TextBlkItem], is_global: bool):
    if is_global:
        blkitems = SW.canvas.selected_text_items()
    else:
        if not isinstance(blkitems, List):
            blkitems = [blkitems]
    values = [values] * len(blkitems)
    return blkitems, values


def should_update_textblk_format(blkitem: TextBlkItem):
    return not blkitem.isEditing() or blkitem.cursor_selects_entire_document()


def update_textblk_format_param(blkitem: TextBlkItem, param_name: str, value):
    if should_update_textblk_format(blkitem) and hasattr(blkitem.fontformat, param_name):
        blkitem.fontformat[param_name] = copy.deepcopy(value)
        if param_name == 'font_weight':
            blkitem.fontformat.bold = int(value) >= 700


def font_formating(push_undostack: bool = False, is_property = True):

    def func_wrapper(formatting_func):

        def wrapper(param_name: str, values: str, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem] = None, set_focus: bool = False, *args, **kwargs):
            if is_global and is_property:
                if hasattr(act_ffmt, param_name):
                    act_ffmt[param_name] = values
                else:
                    print(f'undefined param name: {param_name}')

            blkitems, values = wrap_fntformat_input(values, blkitems, is_global)
            if len(blkitems) > 0:
                if is_property:
                    act_ffmt[param_name] = values[0]
                if push_undostack:
                    params = copy.deepcopy(kwargs)
                    params.update({'param_name': param_name, 'act_ffmt': act_ffmt, 'is_global': is_global, 'blkitems': blkitems})
                    undo_values = [getattr(blkitem.fontformat, param_name) for blkitem in blkitems]
                    cmd = TextStyleUndoCommand(formatting_func, params, values, undo_values)
                    SW.canvas.push_undo_command(cmd)
                else:
                    formatting_func(param_name, values, act_ffmt, is_global, blkitems, *args, **kwargs)
            if set_focus:
                if not SW.canvas.hasFocus():
                    SW.canvas.setFocus()
        return wrapper
    
    return func_wrapper

@font_formating()
def ffmt_change_font_family(param_name: str, values: str, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], **kwargs):
    set_kwargs = global_default_set_kwargs if is_global else local_default_set_kwargs
    for blkitem, value in zip(blkitems, values):
        update_textblk_format_param(blkitem, param_name, value)
        blkitem.setFontFamily(value, **set_kwargs)

@font_formating()
def ffmt_change_italic(param_name: str, values: str, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], **kwargs):
    set_kwargs = global_default_set_kwargs if is_global else local_default_set_kwargs
    for blkitem, value in zip(blkitems, values):
        update_textblk_format_param(blkitem, param_name, value)
        blkitem.setFontItalic(value, **set_kwargs)

@font_formating()
def ffmt_change_underline(param_name: str, values: str, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], **kwargs):
    set_kwargs = global_default_set_kwargs if is_global else local_default_set_kwargs
    for blkitem, value in zip(blkitems, values):
        update_textblk_format_param(blkitem, param_name, value)
        blkitem.setFontUnderline(value, **set_kwargs)

@font_formating()
def ffmt_change_font_weight(param_name: str, values: str, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], **kwargs):
    set_kwargs = global_default_set_kwargs if is_global else local_default_set_kwargs
    for blkitem, value in zip(blkitems, values):
        update_textblk_format_param(blkitem, param_name, value)
        blkitem.setFontWeight(value, **set_kwargs)

@font_formating()
def ffmt_change_bold(param_name: str, values: str, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem] = None, **kwargs):
    set_kwargs = global_default_set_kwargs if is_global else local_default_set_kwargs
    weights = [700 if value else 400 for value in values]
    if weights:
        act_ffmt.font_weight = weights[0]
    for blkitem, weight in zip(blkitems, weights):
        update_textblk_format_param(blkitem, 'font_weight', weight)
        update_textblk_format_param(blkitem, 'bold', weight >= 700)
        blkitem.setFontWeight(weight, **set_kwargs)

@font_formating(push_undostack=True)
def ffmt_change_letter_spacing(param_name: str, values: str, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], **kwargs):
    set_kwargs = global_default_set_kwargs if is_global else local_default_set_kwargs
    for blkitem, value in zip(blkitems, values):
        blkitem.setLetterSpacing(value, **set_kwargs)

@font_formating(push_undostack=True)
def ffmt_change_line_spacing(param_name: str, values: str, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], **kwargs):
    set_kwargs = global_default_set_kwargs if is_global else local_default_set_kwargs
    for blkitem, value in zip(blkitems, values):
        blkitem.setLineSpacing(value, **set_kwargs)

@font_formating(push_undostack=True)
def ffmt_change_vertical(param_name: str, values: bool, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], **kwargs):
    # set_kwargs = global_default_set_kwargs if is_global else local_default_set_kwargs
    for blkitem, value in zip(blkitems, values):
        blkitem.setVertical(value)

@font_formating()
def ffmt_change_frgb(param_name: str, values: tuple, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], **kwargs):
    set_kwargs = global_default_set_kwargs if is_global else local_default_set_kwargs
    for blkitem, value in zip(blkitems, values):
        update_textblk_format_param(blkitem, param_name, value)
        blkitem.setFontColor(value, **set_kwargs)

@font_formating(push_undostack=True)
def ffmt_change_srgb(param_name: str, values: tuple, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], **kwargs):
    set_kwargs = global_default_set_kwargs if is_global else local_default_set_kwargs
    for blkitem, value in zip(blkitems, values):
        update_textblk_format_param(blkitem, param_name, value)
        blkitem.setStrokeColor(value, **set_kwargs)

@font_formating(push_undostack=True)
def ffmt_change_stroke_width(param_name: str, values: float, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], **kwargs):
    set_kwargs = global_default_set_kwargs if is_global else local_default_set_kwargs
    for blkitem, value in zip(blkitems, values):
        blkitem.setStrokeWidth(value, **set_kwargs)

@font_formating()
def ffmt_change_font_size(param_name: str, values: float, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], clip_size=False, **kwargs):
    set_kwargs = global_default_set_kwargs if is_global else local_default_set_kwargs
    for blkitem, value in zip(blkitems, values):
        if value < 0:
            continue
        update_textblk_format_param(blkitem, param_name, value)
        blkitem.setFontSize(px2pt(value), clip_size=clip_size, **set_kwargs)

@font_formating(is_property=False)
def ffmt_change_rel_font_size(param_name: str, values: float, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], clip_size=False, **kwargs):
    set_kwargs = global_default_set_kwargs if is_global else local_default_set_kwargs
    for blkitem, value in zip(blkitems, values):
        if should_update_textblk_format(blkitem):
            blkitem.fontformat.font_size *= value
        blkitem.setRelFontSize(value, clip_size=clip_size, **set_kwargs)

@font_formating(push_undostack=True)
def ffmt_change_alignment(param_name: str, values: float, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], **kwargs):
    restore_cursor = not is_global
    for blkitem, value in zip(blkitems, values):
        blkitem.setAlignment(value, restore_cursor=restore_cursor)

@font_formating(push_undostack=True)
def ffmt_change_opacity(param_name: str, values: float, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], **kwargs):
    for blkitem, value in zip(blkitems, values):
        blkitem.setOpacity(value)

@font_formating(push_undostack=True)
def ffmt_change_line_spacing_type(param_name: str, values: float, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], **kwargs):
    restore_cursor = not is_global
    for blkitem, value in zip(blkitems, values):
        blkitem.setLineSpacingType(value, restore_cursor=restore_cursor)


def ffmt_change_angle(param_name: str, values: float, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem] = None, set_focus: bool = False, **kwargs):
    if is_global:
        blkitems = SW.canvas.selected_text_items()
    elif not isinstance(blkitems, list):
        blkitems = [blkitems]

    blkitems = [blkitem for blkitem in blkitems if blkitem is not None]
    if len(blkitems) > 0:
        SW.canvas.push_undo_command(
            RotateItemCommand(
                blkitems,
                values,
            )
        )

    if set_focus and not SW.canvas.hasFocus():
        SW.canvas.setFocus()


@font_formating(push_undostack=True)
def ffmt_change_shadow_offset(param_name: str, values: float, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], **kwargs):
    for blkitem, value in zip(blkitems, values):
        blkitem.setBGAttribute(param_name, value)


@font_formating()
def ffmt_change_gradient_enabled(param_name: str, values: float, act_ffmt: FontFormat, is_global: bool, blkitems: List[TextBlkItem], **kwargs):
    for blkitem, value in zip(blkitems, values):
        blkitem.setGradientAttribute(param_name, value)


ffmt_change_shadow_radius = ffmt_change_shadow_offset
ffmt_change_shadow_strength = ffmt_change_shadow_offset
ffmt_change_shadow_color = ffmt_change_shadow_offset

ffmt_change_gradient_start_color = ffmt_change_gradient_enabled
ffmt_change_gradient_end_color = ffmt_change_gradient_enabled
ffmt_change_gradient_angle = ffmt_change_gradient_enabled
ffmt_change_gradient_size = ffmt_change_gradient_enabled

handle_ffmt_change = {
    name: globals().get(f'ffmt_change_{name}', empty_func)
    for name in (*FontFormat.params(), 'rel_font_size', 'angle')
}
