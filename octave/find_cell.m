function [j, weight] = find_cell(nodes, x)
  % The grid cell j that holds x and how far x lies into it (docs/model.md Eq. 4, steps 1 to 3), as
  % python/ekfsoc/model.py find_cell, with j counted from 1.
  %
  % nodes is strictly ascending or strictly descending. x is first clamped to the axis ends. lookup()
  % gives the largest index whose node is at or before x_clamped in the axis direction, which is the
  % index of the Python bisection; at the last node it gives n, and the cell is the last one, n - 1.
  n = numel(nodes);
  lowest = min(nodes(1), nodes(n));
  highest = max(nodes(1), nodes(n));
  x_clamped = min(max(x, lowest), highest);
  j = min(lookup(nodes, x_clamped), n - 1);
  weight = (x_clamped - nodes(j)) / (nodes(j + 1) - nodes(j));
end
