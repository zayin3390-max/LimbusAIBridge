"""Wrapping controls and scrollable content using ordinary Tk geometry."""
import tkinter as tk
from tkinter import ttk

class FlowFrame(ttk.Frame):
    def __init__(self,parent,**kwargs):
        super().__init__(parent,**kwargs)
        self.items=[];self.hidden=set();self._pending=None
        self.bind('<Configure>',self.schedule)
    def add(self,widget):
        self.items.append(widget);self.schedule()
        return widget
    def schedule(self,event=None):
        if self._pending is None:self._pending=self.winfo_toplevel().after_idle(self.reflow)
    def set_hidden(self,widgets):
        hidden=set(widgets)
        if hidden!=self.hidden:self.hidden=hidden;self.schedule()
    def reflow(self):
        self._pending=None
        width=max(1,self.winfo_width());row=col=used=0
        for widget in self.items:
            if widget in self.hidden:
                widget.grid_forget();continue
            needed=widget.winfo_reqwidth()+8
            if col and used+needed>width:row+=1;col=0;used=0
            widget.grid(row=row,column=col,sticky='w',padx=(0,8),pady=3)
            used+=needed;col+=1

class ScrollFrame(ttk.Frame):
    def __init__(self,parent,background,**kwargs):
        super().__init__(parent,**kwargs)
        self.canvas=tk.Canvas(self,bg=background,highlightthickness=0)
        self.scroll=ttk.Scrollbar(self,command=self.canvas.yview)
        self.scroll.pack(side='right',fill='y')
        self.canvas.pack(fill='both',expand=True)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.body=ttk.Frame(self.canvas)
        self.window=self.canvas.create_window((0,0),window=self.body,anchor='nw')
        self.canvas.bind('<Configure>',self.resize)
        self.body.bind('<Configure>',self.region)
        self.canvas.bind('<MouseWheel>',self.wheel)
    def resize(self,event):
        self.canvas.itemconfigure(self.window,width=max(1,event.width))
        self.region()
    def region(self,event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
    def wheel(self,event):
        self.canvas.yview_scroll(-int(event.delta/120),'units')
        return 'break'
    def bind_children(self):
        def bind(widget):
            # Text/tree controls retain their own wheel behavior.
            if not isinstance(widget,(tk.Text,ttk.Treeview,ttk.Combobox,ttk.Spinbox)):
                widget.bind('<MouseWheel>',self.wheel,add='+')
            for child in widget.winfo_children():bind(child)
        bind(self.body)
