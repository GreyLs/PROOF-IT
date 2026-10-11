"""Reconstruct a persistent two-column PDF seam using glyph geometry."""
import statistics


def ordered_text(textpage):
    original=textpage.get_text_range()
    if textpage.count_chars()>30000:return original,"pdf_text"
    rows={}
    for i in range(textpage.count_chars()):
        char=textpage.get_text_range(i,1)
        if not char or char in ('\r','\n','\t'):continue
        # Font-wide boxes retain a common baseline despite descenders and
        # preserve actual spaces; tight glyph boxes split "Python" into rows.
        left,bottom,right,top=textpage.get_charbox(i,loose=True)
        if right<=left or top<=bottom:continue
        key=round(bottom/3)*3
        rows.setdefault(key,[]).append((left,right,char))
    lines=[(y,sorted(chars)) for y,chars in sorted(rows.items(),reverse=True)]
    gaps=[]
    for y,chars in lines:
        for first,second in zip(chars,chars[1:]):
            if second[0]-first[1]>60:gaps.append((first[1]+8,second[0]-8,y))
    if len(gaps)<6:return original,"pdf_text"
    points=sorted({int((a+b)/2) for a,b,_ in gaps})
    seam=max(points,key=lambda x:sum(a<=x<=b for a,b,_ in gaps))
    support=sum(a<=seam<=b for a,b,_ in gaps)
    if support<6 or support<.2*len(lines):return original,"pdf_text"
    left_count=sum(x<seam for _,chars in lines for x,_,_ in chars)
    right_count=sum(x>=seam for _,chars in lines for x,_,_ in chars)
    if min(left_count,right_count)<.12*(left_count+right_count):return original,"pdf_text"
    def text(chars):
        values=[];previous=None
        widths=[b-a for a,b,_ in chars];space=max(2,statistics.median(widths)*.55) if widths else 3
        for a,b,char in chars:
            if previous is not None and a-previous>space:values.append(" ")
            values.append(char);previous=b
        return "".join(values)
    first_dual=max(y for a,b,y in gaps if a<=seam<=b)
    headers=[];left=[];right=[]
    for y,chars in lines:
        if y>first_dual+6:headers.append(text(chars));continue
        l=[p for p in chars if p[0]<seam];r=[p for p in chars if p[0]>=seam]
        if l:left.append(text(l))
        if r:right.append(text(r))
    return "\n".join(headers+left+right),"pdf_geometry_two_column"
