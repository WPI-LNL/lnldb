import reversion

def make_changes_string(form):
    if not form:
        return None
    changes_string = ""
    if len(form.changed_data) > 0:
        changes_string += "Fields changed: "
        for field_name in form.changed_data:
            changes_string += field_name + ", "
        changes_string = changes_string[:-2]
    return changes_string

def set_revision_comment(comment, form):
    changes_string = make_changes_string(form)
    if changes_string:
        reversion.set_comment(comment + " - " + changes_string)
    else:
        reversion.set_comment(comment)
