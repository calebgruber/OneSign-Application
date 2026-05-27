<?php
$appBasePath = function_exists('appBasePath') ? appBasePath() : '';
$assetBasePath = $appBasePath . '/assets';
?>
  </div><!-- /page-wrapper -->
</div><!-- /wrapper -->

<script src="https://cdn.jsdelivr.net/npm/@tabler/core@1.0.0-beta20/dist/js/tabler.min.js"></script>
<script src="<?= htmlspecialchars($assetBasePath) ?>/js/admin.js"></script>
</body>
</html>
