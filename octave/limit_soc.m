function x_limited = limit_soc(x_post, P_post)
  % x_post with its SoC limited to [0, 1] (Eq. 10, docs/decisions.md 1.16), as Ekf.limit_soc.
  % Outside [0, 1] the whole state moves onto the nearer bound along the first column of P_post.
  soc_bound = min(max(x_post(1), 0), 1);
  if x_post(1) == soc_bound
    x_limited = x_post;
    return;
  end
  shift = P_post(:, 1) * (x_post(1) - soc_bound) / P_post(1, 1);
  x_limited = x_post - shift;
  x_limited(1) = soc_bound;  % exactly on the bound, whatever the rounding of the line above
end
