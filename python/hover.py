import tkinter as tk
import tkinter.ttk as ttk

class ToolTip(object):
    """
    create a tooltip for a given widget
    """
    def __init__(self, widget, text='widget info', delay=0):
        self.waittime = delay     #miliseconds
        self.wraplength = 320   #pixels
        self.posOffset = (4, 12) #(x,y)
        self.widget = widget
        self.text = text
        self.x = None
        self.y = None
        self.id = None
        self.tw = None
        self.label = None

        # create TK event bindings
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        """ shall ToolTip hide on MouseClick? """
        #self.widget.bind("<ButtonPress>", self.leave)
        """ shall ToolTip position be updated with mouse cursor motion? """
        self.widget.bind("<Motion>", self.motion)

    def enter(self, event):
        """ Entry event, start scheduler for wait time """
        self.x = event.x_root
        self.y = event.y_root
        self.schedule()

    def leave(self, event):
        """ Leave event, hide Tooltip """
        self.unschedule()
        self.hidetip()

    def motion(self, event):
        """ Motion event, update ToolTip position to prevent some event conflicts 
            with Widget item and ToolTip itself (keep distance!) """
        self.x = event.x_root
        self.y = event.y_root
        if self.tw:
            # update ToolTip position once when shown
            x = self.x + self.posOffset[0]
            y = self.y + self.posOffset[1]
            self.tw.wm_geometry("+%d+%d" % (x, y))

    def schedule(self):
        """ Reset timer and prepare for rise of ToolTip message """
        self.unschedule()
        self.id = self.widget.after(self.waittime, self.showtip)

    def unschedule(self):
        """ Drop scheduler """
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)

    def showtip(self):
        """ Create ToolTip message """
        # set position relative to entry point
        x = self.x + self.posOffset[0]
        y = self.y + self.posOffset[1]

        # creates a toplevel window
        self.tw = tk.Toplevel(self.widget)
        # Leaves only the label and removes the app window
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry("+%d+%d" % (x, y))
        self.label = tk.Label(self.tw, text=self.text, justify='left',
            background="#ffffcc", relief='solid', borderwidth=1,
            wraplength = self.wraplength)
        self.label.pack(ipadx=2)

    def hidetip(self):
        """ Kill ToolTip message """
        tw = self.tw
        self.tw= None
        if tw:
            tw.destroy()

class CanvasToolTip(object):
    """
    create a tooltip for a given widget
    """
    def __init__(self, canvas, widget, text='widget info', delay=0, justify='left'):
        self.waittime = delay     #miliseconds
        self.wraplength = 320   #pixels
        self.posOffset = (4, 12) #(x,y)
        self.canvas = canvas
        self.widget = widget
        self.text = text
        self.x = None
        self.y = None
        self.id = None
        self.tw = None
        self.visible = False
        self.label = None
        self.justify = justify

        # create TK event bindings
        self.canvas.tag_bind(self.widget, "<Enter>", self.enter)
        self.canvas.tag_bind(self.widget, "<Leave>", self.leave)
        self.canvas.tag_bind(self.widget, "<Motion>", self.motion)

    def enter(self, event):
        """ Entry event, start scheduler for wait time """
        if not self.visible:
            self.x = event.x_root
            self.y = event.y_root
            self.schedule()
            self.visible = True

    def leave(self, event):
        """ Leave event, hide Tooltip """
        self.unschedule()
        self.hidetip()
        self.visible = False

    def motion(self, event):
        """ Motion event, update ToolTip position to prevent some event conflicts 
            with Widget item and ToolTip itself (keep distance!) """
        self.x = event.x_root
        self.y = event.y_root
        if self.tw:
            # update ToolTip position once when shown
            x = self.x + self.posOffset[0]
            y = self.y + self.posOffset[1]
            self.tw.wm_geometry("+%d+%d" % (x, y))

    def schedule(self):
        """ Reset timer and prepare for rise of ToolTip message """
        self.unschedule()
        self.id = self.canvas.after(self.waittime, self.showtip)

    def unschedule(self):
        """ Drop scheduler """
        id = self.id
        self.id = None
        if id:
            self.canvas.after_cancel(id)

    def updateTip(self, widget, text):
        self.widget = widget
        self.text = text
        try:
            self.label.configure(text=text)
        except:
            pass
        # create TK event bindings
        self.canvas.tag_bind(self.widget, "<Enter>", self.enter)
        self.canvas.tag_bind(self.widget, "<Leave>", self.leave)
        self.canvas.tag_bind(self.widget, "<Motion>", self.motion)

    def showtip(self):
        """ Create ToolTip message """
        # set position relative to entry point
        x = self.x + self.posOffset[0]
        y = self.y + self.posOffset[1]

        # creates a toplevel window
        self.tw = tk.Toplevel(self.canvas)
        # Leaves only the label and removes the app window
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry("+%d+%d" % (x, y))
        self.label = tk.Label(self.tw, text=self.text, justify=self.justify,
            background="#ffffcc", relief='solid', borderwidth=1,
            wraplength = self.wraplength)
        self.label.pack(ipadx=2)

    def hidetip(self):
        """ Kill ToolTip message """
        tw = self.tw
        self.tw= None
        if tw:
            tw.destroy()
    
    def kill(self):
        self.unschedule()
        self.hidetip()
        del self

if __name__ == "__main__":
    app = tk.Tk()
    app.minsize(450, 400)

    myButton = ttk.Button(app, text="click me")
    myButton.pack(pady="2")
    myEntry = tk.Entry(app, text="Write some thinf here")
    myEntry.pack(pady="2")

    # create ToolTips    
    myHover1 = ToolTip(myButton, "Click that Button so it does something wicket!")
    myHover2 = ToolTip(myEntry, "Write something here while the message is shown, it won't harm you!")

    app.mainloop()
