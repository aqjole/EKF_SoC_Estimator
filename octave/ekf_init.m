function ekf = ekf_init(params, cfg, soc0)
  % The filter state x = [SoC; V1; V2] and covariance P at the start of a run, as
  % python/ekfsoc/ekf.py Ekf.__init__. cfg holds q_soc, q_v, r, p0_soc_std and p0_v_std (EkfConfig).
  ekf.params = params;
  ekf.cfg = cfg;
  ekf.q_ref_ah = 2.7807;  % Q_REF_AH of python/ekfsoc/constants.py
  ekf.x = [soc0; 0; 0];
  ekf.P = diag([cfg.p0_soc_std^2, cfg.p0_v_std^2, cfg.p0_v_std^2]);
  ekf.i_held = 0;  % the previous sample's current, held over the next step (docs/model.md C11)
end
